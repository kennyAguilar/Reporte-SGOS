"""Módulo Getnet — sub-menú Dashboard | Histórico | Record Asistentes | Rendimiento.

- Dashboard:         KPIs + gráficos por mes, por hora y mapa de calor.
- Histórico:         resumen mensual y detalle por hora.
- Record Asistentes: lo OPERATIVO por persona (podio de records, conteos por
                     mes/año).
- Rendimiento:       la EVALUACIÓN por persona (promedio por jornada, índice
                     vs equipo, cobertura, constancia, tendencia).

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
    """Lee los filtros de la URL y arma el contexto común de las vistas Getnet.

    El selector de año ofrece los años que realmente tienen datos; si la base
    aún está vacía (o falla), cae a los últimos 6 años como antes.
    """
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    anios = _safe(getnet_repository.get_anios_disponibles) or []
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


@getnet_bp.route("/")
@login_required
def dashboard():
    """Dashboard de Getnet: KPIs + gráficos por mes, por hora y mapa de calor."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    kpis = _safe(getnet_repository.get_kpis_dashboard, anio, mes, nombre)
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


@getnet_bp.route("/historico")
@login_required
def historico():
    """Histórico de Getnet: resumen mensual y operaciones por hora."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    resumen_mensual = _safe(getnet_repository.get_resumen_mensual, anio, mes, nombre)
    ops_hora = _safe(getnet_repository.get_operaciones_por_hora, anio, mes, nombre)

    return render_template(
        "getnet/historico.html",
        user=current_user(),
        active="getnet",
        seccion="historico",
        resumen_mensual=resumen_mensual,
        ops_hora=ops_hora,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@getnet_bp.route("/record-asistentes")
@login_required
def record_asistentes():
    """Record de asistentes Getnet: podio, resumen y transacciones por periodo."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    resumen_asist = _safe(getnet_repository.get_resumen_asistentes, anio, mes, nombre) or []
    # El podio sale del mismo resumen: una sola pasada por la tabla.
    record = getnet_repository.ordenar_por_record(resumen_asist)
    trans_mes = _safe(getnet_repository.get_transacciones_mes_anio, anio, mes, nombre) or []
    total_anio = _safe(getnet_repository.get_total_por_anio, anio, mes, nombre)

    return render_template(
        "getnet/record.html",
        user=current_user(),
        active="getnet",
        seccion="record",
        podio=record[:3],
        record_resto=record[3:],
        resumen_asist=resumen_asist,
        total_ops=sum(r["total"] for r in resumen_asist),
        trans_mes=trans_mes,
        total_anio=total_anio,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@getnet_bp.route("/rendimiento")
@login_required
def rendimiento():
    """Evaluación de desempeño por asistente (operaciones normalizadas por jornada)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    rendimiento = _safe(getnet_repository.get_rendimiento_asistentes, anio, mes, nombre)

    return render_template(
        "getnet/rendimiento.html",
        user=current_user(),
        active="getnet",
        seccion="rendimiento",
        rendimiento=rendimiento,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
