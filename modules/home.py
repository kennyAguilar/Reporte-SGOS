"""Home / Resumen principal — panel de control de todos los módulos.

Muestra, de un vistazo: alertas (módulos rezagados, jefaturas sin área),
una tarjeta por módulo con la métrica del último mes y su variación, la
tendencia de operaciones Getnet + Premios y el estado de la última carga de
cada módulo. Las consultas viven en repositories/home_repository.py.
"""
from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import current_user, login_required
from repositories import home_repository, upload_repository

home_bp = Blueprint("home", __name__)

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si la base no responde, el Home muestra el estado vacío en lugar de fallar.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


@home_bp.route("/")
@login_required
def index():
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    panel = _safe(home_repository.get_panel, anio, mes, nombre)
    cargas = _safe(home_repository.get_estado_cargas) or []
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    anios = _safe(home_repository.get_anios_disponibles) or []
    if not anios:
        anio_actual = datetime.now().year
        anios = list(range(anio_actual, anio_actual - 6, -1))
    if anio and anio.isdigit() and int(anio) not in anios:
        anios = sorted(anios + [int(anio)], reverse=True)

    filtros = {
        "anio": anio,
        "mes": mes,
        "nombre": nombre or "",
        "filas_totales": filas_totales,
    }

    return render_template(
        "home.html",
        user=current_user(),
        panel=panel,
        cargas=cargas,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
