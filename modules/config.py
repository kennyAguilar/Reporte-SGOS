"""Módulo de Configuración (solo administradores).

Tres secciones en una sola página con pestañas:

- Slots activos: activar/desactivar slot attendants para que cuenten (o no) en
  las estadísticas de Getnet.
- Gestión de usuarios: listar y crear usuarios.
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
    return render_template(
        "config/index.html",
        user=current_user(),
        active="config",
        seccion=seccion,
        slots=slots,
        usuarios=usuarios,
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
