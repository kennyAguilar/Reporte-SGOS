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
    """Dashboard de Comps: KPIs + gráficos por mes, por día de la semana,
    top de productos y distribución por categoría."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    resumen = _safe(comps_repository.get_resumen, anio, mes, nombre)
    kpis = _safe(comps_repository.get_kpis_dashboard, anio, mes, nombre)
    cortesias_mes = _safe(comps_repository.get_cortesias_por_mes, anio, mes, nombre)
    montos_mes = _safe(comps_repository.get_montos_por_mes, anio, mes, nombre)
    dia_semana = _safe(comps_repository.get_promedio_por_dia_semana, anio, mes, nombre)
    top_productos = _safe(comps_repository.get_top_productos, anio, mes, nombre)
    categorias = _safe(comps_repository.get_categorias, anio, mes, nombre)
    return render_template(
        "comps/dashboard.html",
        user=current_user(),
        active="comps",
        seccion="dashboard",
        titulo="Dashboard",
        resumen=resumen,
        kpis=kpis,
        cortesias_mes=cortesias_mes,
        montos_mes=montos_mes,
        dia_semana=dia_semana,
        top_productos=top_productos,
        categorias=categorias,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@comps_bp.route("/historico")
@login_required
def historico():
    """Histórico de Comps: detalle Por Categoría (expandible a productos)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    resumen = _safe(comps_repository.get_resumen, anio, mes, nombre)
    categorias = _safe(comps_repository.get_categorias_detalle, anio, mes, nombre)
    return render_template(
        "comps/historico.html",
        user=current_user(),
        active="comps",
        seccion="historico",
        titulo="Histórico",
        resumen=resumen,
        categorias=categorias,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@comps_bp.route("/entrega")
@login_required
def entrega():
    """Entrega de Comps: resumen por jugador (expandible a los jefes que invitaron)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    resumen = _safe(comps_repository.get_resumen, anio, mes, nombre)
    jugadores = _safe(comps_repository.get_resumen_jugadores, anio, mes, nombre)
    return render_template(
        "comps/entrega.html",
        user=current_user(),
        active="comps",
        seccion="entrega",
        titulo="Entrega",
        resumen=resumen,
        jugadores=jugadores,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
