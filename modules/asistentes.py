"""Módulo Asistentes — rendimiento combinado Getnet + Premios.

Una sola vista: por cada slot attendant suma sus operaciones de ambos módulos
y evalúa su desempeño con el mismo modelo que Getnet y Premios (promedio por
jornada, índice vs equipo, cobertura, constancia, tendencia). Solo cuenta
cantidades de operaciones; los montos quedan en cada módulo.
"""
from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import current_user, login_required
from repositories import asistentes_repository, upload_repository

asistentes_bp = Blueprint("asistentes", __name__, url_prefix="/asistentes")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error."""
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _contexto_filtros():
    """Lee los filtros de la URL y arma el contexto común de la vista."""
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    anios = _safe(asistentes_repository.get_anios_disponibles) or []
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
    return anio, mes, nombre, filtros, anios


@asistentes_bp.route("/")
@login_required
def rendimiento():
    """Rendimiento combinado de asistentes (Getnet + Premios)."""
    anio, mes, nombre, filtros, anios = _contexto_filtros()

    rendimiento = _safe(asistentes_repository.get_rendimiento_combinado, anio, mes, nombre)
    ultimo_archivo = _safe(upload_repository.get_ultimo_archivo)

    return render_template(
        "asistentes/rendimiento.html",
        user=current_user(),
        active="asistentes",
        rendimiento=rendimiento,
        ultimo_archivo=ultimo_archivo,
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
