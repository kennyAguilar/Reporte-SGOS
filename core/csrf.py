"""Protección CSRF para los formularios de SGOS (sin dependencias externas).

Funcionamiento:
  - Al renderizar una página, `csrf_token()` genera (una vez por sesión) un
    token aleatorio y lo guarda en la sesión firmada de Flask.
  - Cada formulario POST debe incluir `<input type="hidden" name="_csrf_token"
    value="{{ csrf_token() }}">`.
  - Antes de atender cualquier POST se compara el token del formulario (o la
    cabecera `X-CSRF-Token`) con el de la sesión; si no coinciden se responde
    400. Así un sitio externo no puede disparar acciones con la cookie del
    usuario (desactivar slots, cambiar contraseñas, cargar archivos...).
"""
import hmac
import secrets

from flask import abort, request, session

_SESSION_KEY = "_csrf_token"
_FORM_FIELD = "_csrf_token"
_HEADER = "X-CSRF-Token"


def generar_token():
    """Devuelve el token CSRF de la sesión, creándolo si aún no existe."""
    token = session.get(_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_SESSION_KEY] = token
    return token


def init_csrf(app):
    """Registra la verificación en cada POST y expone `csrf_token()` a Jinja."""

    @app.before_request
    def _verificar_csrf():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        esperado = session.get(_SESSION_KEY)
        recibido = request.form.get(_FORM_FIELD) or request.headers.get(_HEADER)
        if not esperado or not recibido or not hmac.compare_digest(esperado, recibido):
            abort(400, description="Token CSRF inválido o ausente. Recarga la página e intenta de nuevo.")
        return None

    @app.context_processor
    def _inyectar_csrf():
        return {"csrf_token": generar_token}
