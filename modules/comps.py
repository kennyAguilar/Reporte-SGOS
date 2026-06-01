"""Módulo Comps — landing de la sección.

Por ahora solo expone una vista placeholder con el header y el panel de filtros,
de modo que el botón "Cargar Excel" del header funcione contextualmente (apunta a
la carga de COMPS). El dashboard completo se construirá más adelante.

El panel de filtros es el mismo que usa el Home, pero su formulario apunta a la
ruta de este módulo, de modo que al aplicar filtros (o pulsar "Todos") el usuario
se mantiene dentro de Comps.
"""
from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import current_user, login_required
from repositories import comps_repository

comps_bp = Blueprint("comps", __name__, url_prefix="/comps")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si la tabla no tiene datos o aún no está el esquema, la vista muestra el
    estado vacío en lugar de romperse.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _contexto_filtros():
    """Lee los filtros de la URL y arma el contexto común de las vistas Comps."""
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    anio_actual = datetime.now().year
    anios = list(range(anio_actual, anio_actual - 6, -1))

    filtros = {
        "anio": anio,
        "mes": mes,
        "nombre": nombre or "",
        "filas_totales": filas_totales,
    }
    return anio, mes, nombre, filtros, anios


@comps_bp.route("/")
@login_required
def dashboard():
    """Landing de Comps. Sección en construcción; muestra el resumen disponible."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    resumen = _safe(comps_repository.get_resumen, anio, mes, nombre)
    return render_template(
        "comps/placeholder.html",
        user=current_user(),
        active="comps",
        seccion="dashboard",
        titulo="Dashboard",
        resumen=resumen,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
