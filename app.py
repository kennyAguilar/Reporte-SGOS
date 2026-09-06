"""Punto de entrada de SGOS."""
import os

from flask import Flask, render_template

from config import Config
from modules.auth import auth_bp
from modules.coinin import coinin_bp
from modules.coinin_cero import coinin_cero_bp
from modules.comps import comps_bp
from modules.config import config_bp
from modules.getnet import getnet_bp
from modules.home import home_bp
from modules.premios import premios_bp
from modules.upload import upload_bp
from repositories import coinin_repository, config_repository, premios_repository


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.url_defaults
    def _versionar_estaticos(endpoint, values):
        """Agrega ?v=<fecha de modificación> a los archivos estáticos.

        Sin esto, Cloudflare (o el navegador) puede seguir sirviendo una copia
        cacheada de un .js/.css viejo tras un deploy, porque la URL no cambia
        aunque el contenido sí. Al variar la URL en cada cambio real de
        archivo, se fuerza a pedir la versión nueva.
        """
        if endpoint != "static" or "filename" not in values:
            return
        ruta = os.path.join(app.static_folder, values["filename"])
        try:
            values["v"] = int(os.path.getmtime(ruta))
        except OSError:
            pass

    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(getnet_bp)
    app.register_blueprint(premios_bp)
    app.register_blueprint(comps_bp)
    app.register_blueprint(coinin_bp)
    app.register_blueprint(coinin_cero_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(config_bp)

    # Asegura los esquemas que cada módulo necesita (tablas auxiliares).
    # Si la BD no está disponible al arrancar, no impedimos el inicio.
    try:
        config_repository.ensure_schema()
    except Exception:
        pass
    try:
        premios_repository.ensure_premios_schema()
    except Exception:
        pass
    try:
        coinin_repository.ensure_coinin_schema()
    except Exception:
        pass

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template("errors/500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=app.config.get("DEBUG", False),
    )
