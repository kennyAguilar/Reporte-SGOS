"""Módulo Coin In — vistas de los sistemas MDA y MDJ.

Ambos sistemas comparten tabla y consultas (se distinguen por la columna
`sistema`), así que las vistas usan las mismas funciones y solo cambia el
sistema que se pasa al repositorio.
"""
from datetime import datetime

from flask import Blueprint, redirect, render_template, request, url_for

from core.auth import current_user, login_required
from repositories import coinin_repository

coinin_bp = Blueprint("coinin", __name__, url_prefix="/coinin")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si la tabla aún no existe o no hay datos, la vista muestra el estado vacío
    en lugar de romperse.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _contexto_filtros():
    """Lee los filtros de la URL y arma el contexto común de las vistas Coin In."""
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    nivel = (request.args.get("nivel") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    anio_actual = datetime.now().year
    anios = list(range(anio_actual, anio_actual - 6, -1))

    filtros = {
        "anio": anio,
        "mes": mes,
        "nombre": nombre or "",
        "nivel": nivel or "",
        "filas_totales": filas_totales,
    }
    return anio, mes, nombre, nivel, filtros, anios


def _dashboard(sistema):
    anio, mes, nombre, nivel, filtros, anios = _contexto_filtros()
    return render_template(
        "coinin/dashboard.html",
        user=current_user(),
        active="coinin",
        sistema=sistema,
        seccion="dashboard",
        titulo="Dashboard",
        resumen=_safe(coinin_repository.get_resumen, sistema, anio, mes, nombre, nivel),
        kpis=_safe(coinin_repository.get_kpis_dashboard, sistema, anio, mes, nombre, nivel),
        coin_in_mes=_safe(
            coinin_repository.get_coin_in_por_mes, sistema, anio, mes, nombre, nivel
        ),
        jugadores_mes=_safe(
            coinin_repository.get_jugadores_por_mes, sistema, anio, mes, nombre, nivel
        ),
        niveles=_safe(coinin_repository.get_niveles, sistema, anio, mes, nombre, nivel),
        top_jugadores=_safe(
            coinin_repository.get_top_jugadores, sistema, anio, mes, nombre, nivel
        ),
        niveles_disponibles=_safe(coinin_repository.get_niveles_disponibles, sistema),
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


def _historico(sistema):
    anio, mes, nombre, nivel, filtros, anios = _contexto_filtros()
    return render_template(
        "coinin/historico.html",
        user=current_user(),
        active="coinin",
        sistema=sistema,
        seccion="historico",
        titulo="Histórico",
        resumen=_safe(coinin_repository.get_resumen, sistema, anio, mes, nombre, nivel),
        mensual=_safe(
            coinin_repository.get_resumen_mensual, sistema, anio, mes, nombre, nivel
        ),
        niveles=_safe(
            coinin_repository.get_detalle_niveles, sistema, anio, mes, nombre, nivel
        ),
        top_jugadores=_safe(
            coinin_repository.get_top_jugadores, sistema, anio, mes, nombre, nivel, 50
        ),
        niveles_disponibles=_safe(coinin_repository.get_niveles_disponibles, sistema),
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@coinin_bp.route("/")
@login_required
def index():
    return redirect(url_for("coinin.mda_dashboard"))


@coinin_bp.route("/mda")
@login_required
def mda_dashboard():
    return _dashboard("MDA")


@coinin_bp.route("/mda/historico")
@login_required
def mda_historico():
    return _historico("MDA")


@coinin_bp.route("/mdj")
@login_required
def mdj_dashboard():
    return _dashboard("MDJ")


@coinin_bp.route("/mdj/historico")
@login_required
def mdj_historico():
    return _historico("MDJ")
