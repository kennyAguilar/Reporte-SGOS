"""Autenticación y control de sesión de SGOS."""
from functools import wraps

from flask import redirect, session, url_for


def login_required(view):
    """Protege una vista exigiendo sesión activa."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def current_user():
    """Devuelve los datos del usuario en sesión, o None."""
    if not session.get("user_id"):
        return None
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "is_admin": session.get("is_admin", False),
    }
