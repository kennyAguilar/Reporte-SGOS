"""Módulo Getnet — sub-menú Dashboard | Histórico | Record Asistentes.

Por ahora solo el Dashboard está implementado. Histórico y Record Asistentes
quedan como vistas placeholder, listas para construir más adelante.

El panel de filtros es el mismo que usa el Home, pero su formulario apunta a la
ruta de este módulo, de modo que al aplicar filtros (o pulsar "Todos") el usuario
se mantiene dentro de Getnet.
"""
from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import current_user, login_required
from repositories import getnet_repository, upload_repository

getnet_bp = Blueprint("getnet", __name__, url_prefix="/getnet")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si la tabla no tiene datos o aún no está el esquema, el dashboard muestra el
    estado vacío en lugar de romperse.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _contexto_filtros():
    """Lee los filtros de la URL y arma el contexto común de las vistas Getnet."""
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


@getnet_bp.route("/")
@login_required
def dashboard():
    """Dashboard de Getnet: KPIs + gráficos por mes, por hora y mapa de calor."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    resumen = _safe(getnet_repository.get_resumen, anio, mes, nombre)
    ops_mes = _safe(getnet_repository.get_operaciones_por_mes, anio, mes, nombre)
    montos_mes = _safe(getnet_repository.get_montos_por_mes, anio, mes, nombre)
    promedio_hora = _safe(getnet_repository.get_promedio_por_hora, anio, mes, nombre)
    heatmap = _safe(getnet_repository.get_heatmap_dia_hora, anio, mes, nombre)
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    return render_template(
        "getnet/dashboard.html",
        user=current_user(),
        active="getnet",
        seccion="dashboard",
        resumen=resumen,
        ops_mes=ops_mes,
        montos_mes=montos_mes,
        promedio_hora=promedio_hora,
        heatmap=heatmap,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@getnet_bp.route("/historico")
@login_required
def historico():
    """Histórico de operaciones Getnet (pendiente de construir)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)
    return render_template(
        "getnet/placeholder.html",
        user=current_user(),
        active="getnet",
        seccion="historico",
        titulo="Histórico",
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@getnet_bp.route("/record-asistentes")
@login_required
def record_asistentes():
    """Record de asistentes Getnet (pendiente de construir)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)
    return render_template(
        "getnet/placeholder.html",
        user=current_user(),
        active="getnet",
        seccion="record",
        titulo="Record Asistentes",
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
