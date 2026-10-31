"""Rutas de autenticación: login, logout y cambio de la propia contraseña."""
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from core.auth import current_user, login_required
from repositories.usuarios_repository import (
    get_password_hash,
    get_user_by_username,
    update_last_login,
    update_password,
)

auth_bp = Blueprint("auth", __name__)

# Largo mínimo de contraseña para altas y cambios (aquí y en Configuración).
PASSWORD_MIN = 8


def validar_password(password, password2=None):
    """Devuelve un mensaje de error o None si la contraseña es aceptable."""
    if not password:
        return "La contraseña es obligatoria."
    if len(password) < PASSWORD_MIN:
        return f"La contraseña debe tener al menos {PASSWORD_MIN} caracteres."
    if password2 is not None and password != password2:
        return "Las contraseñas no coinciden."
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("home.index"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            error = "Usuario y contraseña son obligatorios."
        else:
            user = None
            try:
                user = get_user_by_username(username)
            except Exception:
                error = (
                    "No fue posible conectar con la base de datos. "
                    "Intente nuevamente o contacte al administrador."
                )

            if error is None:
                if user and check_password_hash(user["password_hash"], password):
                    if not user.get("activo", True):
                        error = "Tu cuenta está desactivada. Contacta al administrador."
                    else:
                        csrf = session.get("_csrf_token")
                        session.clear()
                        if csrf:
                            session["_csrf_token"] = csrf
                        session["user_id"] = user["id"]
                        session["username"] = user["username"]
                        session["is_admin"] = user["is_admin"]
                        try:
                            update_last_login(user["id"])
                        except Exception:
                            pass
                        return redirect(url_for("home.index"))
                if error is None:
                    error = "Credenciales inválidas."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/mi-contrasena", methods=["GET", "POST"])
@login_required
def mi_password():
    """Permite a cualquier usuario cambiar su propia contraseña."""
    user = current_user()
    if request.method == "POST":
        actual = request.form.get("actual") or ""
        nueva = request.form.get("password") or ""
        nueva2 = request.form.get("password2") or ""

        error = validar_password(nueva, nueva2)
        if error is None:
            try:
                hash_actual = get_password_hash(user["id"])
                if not hash_actual or not check_password_hash(hash_actual, actual):
                    error = "La contraseña actual no es correcta."
                elif actual == nueva:
                    error = "La nueva contraseña debe ser distinta de la actual."
                else:
                    update_password(user["id"], generate_password_hash(nueva))
                    flash("Contraseña actualizada.", "success")
                    return redirect(url_for("home.index"))
            except Exception:
                error = "No se pudo actualizar la contraseña. Intenta nuevamente."
        flash(error, "error")

    return render_template("mi_password.html", user=user, active="", password_min=PASSWORD_MIN)
