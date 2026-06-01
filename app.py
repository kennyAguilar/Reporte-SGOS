"""Punto de entrada de SGOS."""
from flask import Flask, render_template

from config import Config
from modules.auth import auth_bp
from modules.comps import comps_bp
from modules.config import config_bp
from modules.getnet import getnet_bp
from modules.home import home_bp
from modules.premios import premios_bp
from modules.upload import upload_bp
from repositories import config_repository, premios_repository


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(getnet_bp)
    app.register_blueprint(premios_bp)
    app.register_blueprint(comps_bp)
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
