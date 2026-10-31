"""Módulo de Configuración (solo administradores).

Cuatro secciones en una sola página con pestañas:

- Slots activos: activar/desactivar slot attendants para que cuenten (o no) en
  las estadísticas de Getnet, Premios y Asistentes.
- Gestión de usuarios: crear, activar/desactivar, cambiar rol, eliminar y
  restablecer contraseñas. Con protecciones: no puedes desactivarte, quitarte
  el rol ni eliminarte a ti mismo, ni dejar el sistema sin administradores.
- Jefaturas: datos maestros (usuario_id, nombre, área) para el módulo COMPS.
- Categorías: % de margen por categoría de jugador (Primario no se elimina).

Toda acción se hace por POST y redirige de vuelta (patrón PRG) con un mensaje
flash para evitar reenvíos al recargar. El cambio de la PROPIA contraseña está
en /mi-contrasena (modules/auth.py) y lo puede usar cualquier usuario.
"""
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core.auth import admin_required, current_user
from modules.auth import PASSWORD_MIN, validar_password
from repositories import config_repository

config_bp = Blueprint("config", __name__, url_prefix="/configuracion")


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error."""
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


@config_bp.route("/")
@admin_required
def index():
    """Página de configuración con sus secciones."""
    _safe(config_repository.ensure_schema)
    seccion = request.args.get("seccion") or "slots"
    if seccion == "password":
        seccion = "usuarios"

    slots = _safe(config_repository.list_slot_attendants)
    usuarios = _safe(config_repository.list_users)
    jefaturas = _safe(config_repository.list_jefaturas)
    areas = _safe(config_repository.list_areas)
    categorias_margen = _safe(config_repository.list_categorias_margen)
    # None = la consulta falló (BD caída o esquema incompleto); [] = sin datos.
    error_bd = any(x is None for x in (slots, usuarios, jefaturas, categorias_margen))

    slots = slots or []
    return render_template(
        "config/index.html",
        user=current_user(),
        active="config",
        seccion=seccion,
        slots=slots,
        slots_activos=sum(1 for s in slots if s["activo"]),
        usuarios=usuarios or [],
        jefaturas=jefaturas or [],
        areas=areas or [],
        categorias_margen=categorias_margen or [],
        error_bd=error_bd,
        password_min=PASSWORD_MIN,
    )


@config_bp.route("/slots/toggle", methods=["POST"])
@admin_required
def toggle_slot():
    """Activa o desactiva un slot attendant."""
    nombre = (request.form.get("nombre") or "").strip()
    activo = request.form.get("activo") == "true"
    if nombre:
        try:
            config_repository.set_slot_activo(nombre, activo)
            estado = "activado" if activo else "desactivado"
            flash(f"«{nombre}» {estado}.", "success")
        except Exception:
            flash("No se pudo actualizar el estado del slot.", "error")
    return redirect(url_for("config.index", seccion="slots"))


@config_bp.route("/usuarios", methods=["POST"])
@admin_required
def crear_usuario():
    """Crea un nuevo usuario."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    is_admin = request.form.get("is_admin") == "on"

    error = None if username else "El nombre de usuario es obligatorio."
    error = error or validar_password(password)
    if error:
        flash(error, "error")
    else:
        try:
            creado = config_repository.create_user(username, password, is_admin)
            if creado:
                flash(f"Usuario «{username}» creado.", "success")
            else:
                flash(f"El usuario «{username}» ya existe.", "error")
        except Exception:
            flash("No se pudo crear el usuario.", "error")
    return redirect(url_for("config.index", seccion="usuarios"))


def _usuario_objetivo():
    """Lee el id del formulario y devuelve (usuario, error). El usuario es un dict."""
    raw = (request.form.get("id") or "").strip()
    if not raw.isdigit():
        return None, "Usuario no válido."
    usuario = config_repository.get_user(int(raw))
    if not usuario:
        return None, "No existe el usuario."
    return usuario, None


def _protege_ultimo_admin(usuario, accion):
    """Mensaje de error si la acción dejaría el sistema sin administradores activos."""
    if usuario["is_admin"] and usuario["activo"]:
        if config_repository.count_admins_activos(excluir_id=usuario["id"]) == 0:
            return f"No se puede {accion}: es el único administrador activo."
    return None


@config_bp.route("/usuarios/activo", methods=["POST"])
@admin_required
def toggle_usuario_activo():
    """Activa o desactiva un usuario (un usuario inactivo no puede iniciar sesión)."""
    yo = current_user()
    activar = request.form.get("activo") == "true"
    try:
        usuario, error = _usuario_objetivo()
        if not error and not activar:
            if usuario["id"] == yo["id"]:
                error = "No puedes desactivar tu propia cuenta."
            else:
                error = _protege_ultimo_admin(usuario, "desactivar")
        if error:
            flash(error, "error")
        else:
            config_repository.set_user_activo(usuario["id"], activar)
            estado = "activado" if activar else "desactivado"
            flash(f"Usuario «{usuario['username']}» {estado}.", "success")
    except Exception:
        flash("No se pudo actualizar el usuario.", "error")
    return redirect(url_for("config.index", seccion="usuarios"))


@config_bp.route("/usuarios/admin", methods=["POST"])
@admin_required
def toggle_usuario_admin():
    """Otorga o quita el rol de administrador."""
    yo = current_user()
    hacer_admin = request.form.get("is_admin") == "true"
    try:
        usuario, error = _usuario_objetivo()
        if not error and not hacer_admin:
            if usuario["id"] == yo["id"]:
                error = "No puedes quitarte el rol de administrador a ti mismo."
            else:
                error = _protege_ultimo_admin(usuario, "quitar el rol")
        if error:
            flash(error, "error")
        else:
            config_repository.set_user_admin(usuario["id"], hacer_admin)
            rol = "administrador" if hacer_admin else "usuario"
            flash(f"«{usuario['username']}» ahora es {rol}.", "success")
    except Exception:
        flash("No se pudo actualizar el rol.", "error")
    return redirect(url_for("config.index", seccion="usuarios"))


@config_bp.route("/usuarios/eliminar", methods=["POST"])
@admin_required
def eliminar_usuario():
    """Elimina un usuario definitivamente."""
    yo = current_user()
    try:
        usuario, error = _usuario_objetivo()
        if not error:
            if usuario["id"] == yo["id"]:
                error = "No puedes eliminar tu propia cuenta."
            else:
                error = _protege_ultimo_admin(usuario, "eliminar")
        if error:
            flash(error, "error")
        else:
            config_repository.delete_user(usuario["id"])
            flash(f"Usuario «{usuario['username']}» eliminado.", "success")
    except Exception:
        flash("No se pudo eliminar el usuario.", "error")
    return redirect(url_for("config.index", seccion="usuarios"))


@config_bp.route("/usuarios/password", methods=["POST"])
@admin_required
def cambiar_password_usuario():
    """Restablece la contraseña de un usuario (acción por fila)."""
    password = request.form.get("password") or ""
    try:
        usuario, error = _usuario_objetivo()
        error = error or validar_password(password)
        if error:
            flash(error, "error")
        else:
            config_repository.reset_password_by_id(usuario["id"], password)
            flash(f"Contraseña actualizada para «{usuario['username']}».", "success")
    except Exception:
        flash("No se pudo actualizar la contraseña.", "error")
    return redirect(url_for("config.index", seccion="usuarios"))


@config_bp.route("/password", methods=["POST"])
@admin_required
def cambiar_password():
    """Restablece la contraseña de un usuario por username (compatibilidad)."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    error = None if username else "El usuario es obligatorio."
    error = error or validar_password(password, password2)
    if error:
        flash(error, "error")
    else:
        try:
            ok = config_repository.reset_password(username, password)
            if ok:
                flash(f"Contraseña actualizada para «{username}».", "success")
            else:
                flash(f"No existe el usuario «{username}».", "error")
        except Exception:
            flash("No se pudo actualizar la contraseña.", "error")
    return redirect(url_for("config.index", seccion="usuarios"))


@config_bp.route("/jefaturas", methods=["POST"])
@admin_required
def crear_jefatura():
    """Crea una nueva jefatura."""
    usuario_id = (request.form.get("usuario_id") or "").strip()
    nombre = (request.form.get("nombre") or "").strip()
    area = (request.form.get("area") or "").strip()

    if not usuario_id or not nombre:
        flash("ID de usuario y nombre son obligatorios.", "error")
    else:
        try:
            creado = config_repository.create_jefatura(usuario_id, nombre, area)
            if creado:
                flash(f"Jefatura «{nombre}» creada.", "success")
            else:
                flash(f"El ID de usuario «{usuario_id}» ya existe.", "error")
        except Exception:
            flash("No se pudo crear la jefatura.", "error")
    return redirect(url_for("config.index", seccion="jefaturas"))


@config_bp.route("/jefaturas/editar", methods=["POST"])
@admin_required
def editar_jefatura():
    """Actualiza una jefatura existente."""
    id = (request.form.get("id") or "").strip()
    usuario_id = (request.form.get("usuario_id") or "").strip()
    nombre = (request.form.get("nombre") or "").strip()
    area = (request.form.get("area") or "").strip()

    if not id or not usuario_id or not nombre:
        flash("ID de usuario y nombre son obligatorios.", "error")
    else:
        try:
            ok = config_repository.update_jefatura(id, usuario_id, nombre, area)
            if ok:
                flash(f"Jefatura «{nombre}» actualizada.", "success")
            else:
                flash("No se encontró la jefatura.", "error")
        except Exception:
            flash("No se pudo actualizar la jefatura.", "error")
    return redirect(url_for("config.index", seccion="jefaturas"))


@config_bp.route("/jefaturas/eliminar", methods=["POST"])
@admin_required
def eliminar_jefatura():
    """Elimina una jefatura."""
    id = (request.form.get("id") or "").strip()
    if not id:
        flash("Jefatura no válida.", "error")
    else:
        try:
            ok = config_repository.delete_jefatura(id)
            if ok:
                flash("Jefatura eliminada.", "success")
            else:
                flash("No se encontró la jefatura.", "error")
        except Exception:
            flash("No se pudo eliminar la jefatura.", "error")
    return redirect(url_for("config.index", seccion="jefaturas"))


@config_bp.route("/categorias", methods=["POST"])
@admin_required
def crear_categoria_margen():
    """Crea una nueva categoría con su % de margen."""
    categoria = (request.form.get("categoria") or "").strip()
    porcentaje_raw = (request.form.get("porcentaje") or "").strip().replace(",", ".")

    if not categoria or not porcentaje_raw:
        flash("Categoría y porcentaje son obligatorios.", "error")
    else:
        try:
            porcentaje = float(porcentaje_raw)
        except ValueError:
            flash("El porcentaje debe ser un número.", "error")
        else:
            try:
                creado = config_repository.create_categoria_margen(categoria, porcentaje)
                if creado:
                    flash(f"Categoría «{categoria}» creada.", "success")
                else:
                    flash(f"La categoría «{categoria}» ya existe.", "error")
            except Exception:
                flash("No se pudo crear la categoría.", "error")
    return redirect(url_for("config.index", seccion="categorias"))


@config_bp.route("/categorias/editar", methods=["POST"])
@admin_required
def editar_categoria_margen():
    """Actualiza una categoría existente."""
    id = (request.form.get("id") or "").strip()
    categoria = (request.form.get("categoria") or "").strip()
    porcentaje_raw = (request.form.get("porcentaje") or "").strip().replace(",", ".")

    if not id or not categoria or not porcentaje_raw:
        flash("Categoría y porcentaje son obligatorios.", "error")
    else:
        try:
            porcentaje = float(porcentaje_raw)
        except ValueError:
            flash("El porcentaje debe ser un número.", "error")
        else:
            try:
                ok = config_repository.update_categoria_margen(id, categoria, porcentaje)
                if ok:
                    flash(f"Categoría «{categoria}» actualizada.", "success")
                else:
                    flash("No se encontró la categoría.", "error")
            except Exception:
                flash("No se pudo actualizar la categoría.", "error")
    return redirect(url_for("config.index", seccion="categorias"))


@config_bp.route("/categorias/eliminar", methods=["POST"])
@admin_required
def eliminar_categoria_margen():
    """Elimina una categoría (Primario está protegida)."""
    id = (request.form.get("id") or "").strip()
    if not id:
        flash("Categoría no válida.", "error")
    else:
        try:
            ok = config_repository.delete_categoria_margen(id)
            if ok:
                flash("Categoría eliminada.", "success")
            else:
                flash("No se encontró la categoría.", "error")
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception:
            flash("No se pudo eliminar la categoría.", "error")
    return redirect(url_for("config.index", seccion="categorias"))
