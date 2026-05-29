"""Rutas de autenticación: login y logout."""
from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from repositories.usuarios_repository import (
    get_user_by_username,
    update_last_login,
)

auth_bp = Blueprint("auth", __name__)


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
                    session.clear()
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session["is_admin"] = user["is_admin"]
                    try:
                        update_last_login(user["id"])
                    except Exception:
                        pass
                    return redirect(url_for("home.index"))
                error = "Credenciales inválidas."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
