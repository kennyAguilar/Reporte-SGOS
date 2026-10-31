"""Módulo Premios — sub-menú Dashboard | Histórico | Record Asistentes | Rendimiento.

- Dashboard:         KPIs + gráficos por mes, por hora y mapa de calor.
- Histórico:         resumen mensual, detalle por hora y conteo máquina × tipo.
- Record Asistentes: lo OPERATIVO por persona (podio de records, conteos por
                     tipo de pago, mes y año).
- Rendimiento:       la EVALUACIÓN por persona (promedio por jornada, índice
                     vs equipo, cobertura, constancia, tendencia).

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
    """Lee los filtros de la URL y arma el contexto común de las vistas Premios.

    El selector de año ofrece los años que realmente tienen datos; si la base
    aún está vacía (o falla), cae a los últimos 6 años como antes.
    """
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    anios = _safe(premios_repository.get_anios_disponibles) or []
    if not anios:
        anio_actual = datetime.now().year
        anios = list(range(anio_actual, anio_actual - 6, -1))
    # Mantiene visible un año pedido por URL aunque no tenga datos.
    if anio and anio.isdigit() and int(anio) not in anios:
        anios = sorted(anios + [int(anio)], reverse=True)

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

    resumen_asist = _safe(premios_repository.get_resumen_asistentes_tipos, anio, mes, nombre)
    # El podio sale del mismo resumen: una sola pasada por la tabla.
    record = premios_repository.ordenar_por_record(resumen_asist["filas"]) if resumen_asist else []
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


@premios_bp.route("/rendimiento")
@login_required
def rendimiento():
    """Evaluación de desempeño por asistente (transacciones normalizadas por jornada)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo, "premios")

    rendimiento = _safe(premios_repository.get_rendimiento_asistentes, anio, mes, nombre)

    return render_template(
        "premios/rendimiento.html",
        user=current_user(),
        active="premios",
        seccion="rendimiento",
        rendimiento=rendimiento,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
