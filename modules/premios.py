"""Módulo Premios — sub-menú Dashboard | Histórico | Record Asistentes.

Por ahora solo el Dashboard está implementado. Histórico y Record Asistentes
quedan como vistas placeholder, listas para construir más adelante.

Esta página fija `active="premios"`, de modo que el header sabe en qué módulo
estás y el botón "Cargar Excel" apunta a la carga de Premios (/upload/premios).
"""
from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import current_user, login_required
from repositories import premios_repository, upload_repository

premios_bp = Blueprint("premios", __name__, url_prefix="/premios")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si la tabla aún no tiene datos, la vista muestra el estado vacío en lugar
    de romperse.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _contexto_filtros():
    """Lee los filtros de la URL y arma el contexto común de las vistas Premios."""
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


@premios_bp.route("/")
@login_required
def dashboard():
    """Dashboard de Premios: KPIs + gráficos por mes, por hora y mapa de calor."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    resumen = _safe(premios_repository.get_resumen, anio, mes, nombre)
    kpis = _safe(premios_repository.get_kpis_dashboard, anio, mes, nombre)
    ops_mes = _safe(premios_repository.get_operaciones_por_mes, anio, mes, nombre)
    montos_mes = _safe(premios_repository.get_montos_por_mes, anio, mes, nombre)
    promedio_hora = _safe(premios_repository.get_promedio_por_hora, anio, mes, nombre)
    heatmap = _safe(premios_repository.get_heatmap_dia_hora, anio, mes, nombre)
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo, "premios")

    return render_template(
        "premios/dashboard.html",
        user=current_user(),
        active="premios",
        seccion="dashboard",
        resumen=resumen,
        kpis=kpis,
        ops_mes=ops_mes,
        montos_mes=montos_mes,
        promedio_hora=promedio_hora,
        heatmap=heatmap,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@premios_bp.route("/historico")
@login_required
def historico():
    """Histórico de Premios: resumen mensual, operaciones por hora y conteo anual."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo, "premios")

    resumen_mensual = _safe(premios_repository.get_resumen_mensual, anio, mes, nombre)
    ops_hora = _safe(premios_repository.get_operaciones_por_hora, anio, mes, nombre)
    conteo_anual = _safe(premios_repository.get_conteo_maquina_tipo, anio, mes, nombre)

    return render_template(
        "premios/historico.html",
        user=current_user(),
        active="premios",
        seccion="historico",
        resumen_mensual=resumen_mensual,
        ops_hora=ops_hora,
        conteo_anual=conteo_anual,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@premios_bp.route("/record-asistentes")
@login_required
def record_asistentes():
    """Record de asistentes de Premios: podio, resumen por tipo y por periodo."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo, "premios")

    record = _safe(premios_repository.get_record_jornadas, anio, mes, nombre) or []
    resumen_asist = _safe(premios_repository.get_resumen_asistentes_tipos, anio, mes, nombre)
    trans_mes = _safe(premios_repository.get_transacciones_mes_anio, anio, mes, nombre) or []
    total_anio = _safe(premios_repository.get_total_por_anio, anio, mes, nombre)
    distribucion = _safe(premios_repository.get_distribucion_tipos, anio, mes, nombre)

    return render_template(
        "premios/record.html",
        user=current_user(),
        active="premios",
        seccion="record",
        podio=record[:3],
        record_resto=record[3:],
        resumen_asist=resumen_asist,
        trans_mes=trans_mes,
        total_anio=total_anio,
        distribucion=distribucion,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
