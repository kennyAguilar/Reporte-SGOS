"""Punto de entrada de SGOS."""
from flask import Flask, render_template

from config import Config
from modules.auth import auth_bp
from modules.getnet import getnet_bp
from modules.home import home_bp
from modules.upload import upload_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.register_blueprint(auth_bp)
    app.register_blueprint(home_bp)
    app.register_blueprint(getnet_bp)
    app.register_blueprint(upload_bp)

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
