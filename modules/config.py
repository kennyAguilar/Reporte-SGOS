"""Módulo de Configuración (solo administradores).

Tres secciones en una sola página con pestañas:

- Slots activos: activar/desactivar slot attendants para que cuenten (o no) en
  las estadísticas de Getnet.
- Gestión de usuarios: listar y crear usuarios.
- Jefaturas: datos maestros (usuario_id, nombre, área) para el módulo COMPS.
- Cambiar contraseña: restablecer la clave de cualquier usuario.

Toda acción se hace por POST y redirige de vuelta (patrón PRG) con un mensaje
flash para evitar reenvíos al recargar.
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
from repositories import config_repository

config_bp = Blueprint("config", __name__, url_prefix="/configuracion")


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a [] / None ante cualquier error."""
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


@config_bp.route("/")
@admin_required
def index():
    """Página de configuración con las tres secciones."""
    _safe(config_repository.ensure_schema)
    seccion = request.args.get("seccion") or "slots"
    slots = _safe(config_repository.list_slot_attendants) or []
    usuarios = _safe(config_repository.list_users) or []
    jefaturas = _safe(config_repository.list_jefaturas) or []
    areas = _safe(config_repository.list_areas) or []
    categorias_margen = _safe(config_repository.list_categorias_margen) or []
    return render_template(
        "config/index.html",
        user=current_user(),
        active="config",
        seccion=seccion,
        slots=slots,
        usuarios=usuarios,
        jefaturas=jefaturas,
        areas=areas,
        categorias_margen=categorias_margen,
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

    if not username or not password:
        flash("Usuario y contraseña son obligatorios.", "error")
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


@config_bp.route("/password", methods=["POST"])
@admin_required
def cambiar_password():
    """Restablece la contraseña de un usuario."""
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    password2 = request.form.get("password2") or ""

    if not username or not password:
        flash("Usuario y contraseña son obligatorios.", "error")
    elif password != password2:
        flash("Las contraseñas no coinciden.", "error")
    else:
        try:
            ok = config_repository.reset_password(username, password)
            if ok:
                flash(f"Contraseña actualizada para «{username}».", "success")
            else:
                flash(f"No existe el usuario «{username}».", "error")
        except Exception:
            flash("No se pudo actualizar la contraseña.", "error")
    return redirect(url_for("config.index", seccion="password"))


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
    """Elimina una categoría."""
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
        except Exception:
            flash("No se pudo eliminar la categoría.", "error")
    return redirect(url_for("config.index", seccion="categorias"))
