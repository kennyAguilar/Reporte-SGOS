"""Home / Resumen principal."""
from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import current_user, login_required
from repositories import (
    comps_repository,
    getnet_repository,
    premios_repository,
    upload_repository,
)

home_bp = Blueprint("home", __name__)

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta de repositorio degradando a None ante cualquier error.

    Las tablas de módulos pueden no tener datos o un esquema aún no confirmado;
    en ese caso el Home muestra el estado vacío en lugar de fallar.
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

    getnet = _safe(getnet_repository.get_resumen, anio, mes, nombre)
    premios = _safe(premios_repository.get_resumen, anio, mes, nombre)
    comps = _safe(comps_repository.get_resumen, anio, mes, nombre)
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    anio_actual = datetime.now().year
    anios = list(range(anio_actual, anio_actual - 6, -1))

    filtros = {
        "anio": anio,
        "mes": mes,
        "nombre": nombre or "",
        "filas_totales": filas_totales,
    }

    return render_template(
        "home.html",
        user=current_user(),
        getnet=getnet,
        premios=premios,
        comps=comps,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
