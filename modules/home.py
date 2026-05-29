"""Home / Resumen principal."""
from flask import Blueprint, render_template

from core.auth import current_user, login_required

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
@login_required
def index():
    return render_template("home.html", user=current_user())
