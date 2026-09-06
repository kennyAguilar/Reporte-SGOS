"""Módulo Coin In Cero — cortesías entregadas a jugadores que no jugaron.

Responde tres cosas de una sola vista:
  1. Quién recibió comps y tuvo Coin In cero esa jornada.
  2. Qué jefe (y de qué área) le entregó esas cortesías.
  3. Si además cobró un premio ese mismo día.

No tiene carga propia: se alimenta de los módulos Comps, Coin In y Premios
(ver repositories/coinin_cero_repository.py para las llaves del cruce).
"""
from datetime import datetime

from flask import Blueprint, render_template, request, url_for

from core.auth import current_user, login_required
from core.formato import miles, pesos
from repositories import coinin_cero_repository

coinin_cero_bp = Blueprint("coinin_cero", __name__, url_prefix="/coinin-cero")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]

# Orden de presentación del Detalle cuando no hay un área filtrada: MDA, MDJ y
# MRK primero (orden pedido por el usuario); cualquier otra área (incluida
# "Auto atención") va después, en el orden que devuelva la base.
_ORDEN_AREAS = ["MDA", "MDJ", "MRK"]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si alguno de los tres módulos que se cruzan aún no tiene datos, la vista
    muestra el estado vacío en lugar de romperse.
    """
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def _contexto_filtros():
    """Lee los filtros de la URL y arma el contexto común de las vistas."""
    anio = request.args.get("anio") or None
    mes = request.args.get("mes") or None
    nombre = (request.args.get("nombre") or "").strip() or None
    area = (request.args.get("area") or "").strip() or None
    filas_totales = request.args.get("filas_totales") == "on"

    anio_actual = datetime.now().year
    anios = list(range(anio_actual, anio_actual - 6, -1))

    filtros = {
        "anio": anio,
        "mes": mes,
        "nombre": nombre or "",
        "area": area or "",
        "filas_totales": filas_totales,
    }
    return anio, mes, nombre, area, filtros, anios


@coinin_cero_bp.route("/")
@login_required
def dashboard():
    """KPIs del fenómeno, evolución mensual, reparto por área y ranking de jefes."""
    anio, mes, nombre, area, filtros, anios = _contexto_filtros()
    return render_template(
        "coinin_cero/dashboard.html",
        user=current_user(),
        active="coinin_cero",
        seccion="dashboard",
        titulo="Dashboard",
        resumen=_safe(coinin_cero_repository.get_resumen, anio, mes, nombre, area),
        kpis=_safe(coinin_cero_repository.get_kpis_dashboard, anio, mes, nombre, area),
        casos_mes=_safe(coinin_cero_repository.get_casos_por_mes, anio, mes, nombre, area),
        areas=_safe(coinin_cero_repository.get_areas, anio, mes, nombre, area),
        jefes=_safe(coinin_cero_repository.get_ranking_jefes, anio, mes, nombre, area),
        sin_cruce=_safe(coinin_cero_repository.get_sin_cruce, anio, mes, nombre, area),
        areas_disponibles=_safe(coinin_cero_repository.get_areas_disponibles),
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


def _etiqueta_area(area):
    """Nombre para mostrar de un área ("Auto atención" se muestra como máquina)."""
    return "Máquinas Autoatención" if area == "Auto atención" else area


def _ordenar_areas(areas):
    """MDA, MDJ, MRK primero; el resto (ej. Auto atención) al final."""
    conocidas = [a for a in _ORDEN_AREAS if a in areas]
    resto = [a for a in areas if a not in _ORDEN_AREAS]
    return conocidas + resto


def _url_pestana(area, filtros):
    """URL de la pestaña de un área, preservando los demás filtros activos."""
    args = {"area": area}
    if filtros["anio"]:
        args["anio"] = filtros["anio"]
    if filtros["mes"]:
        args["mes"] = filtros["mes"]
    if filtros["nombre"]:
        args["nombre"] = filtros["nombre"]
    return url_for("coinin_cero.detalle", **args)


def _grupo_area(area, anio, mes, nombre):
    """Arma el grupo del Detalle para un área: sus jugadores + resumen."""
    jugadores = _safe(coinin_cero_repository.get_detalle, anio, mes, nombre, area)
    resumen = None
    if jugadores:
        casos = sum(j["jornadas_n"] for j in jugadores)
        monto = sum(j["monto"] for j in jugadores)
        resumen = {
            "jugadores": miles(len(jugadores)),
            "casos": miles(casos),
            "monto": pesos(monto),
        }
    return {
        "area": area,
        "label": _etiqueta_area(area),
        "jugadores": jugadores,
        "resumen": resumen,
    }


@coinin_cero_bp.route("/detalle")
@login_required
def detalle():
    """Detalle expandible: jugador → jornadas sin juego, con jefe y premio.

    Se navega por pestañas de área (MDA | MDJ | MRK | Máquinas Autoatención):
    solo se consulta y muestra la pestaña activa, igual que Coin In con MDA/MDJ.
    """
    anio, mes, nombre, area, filtros, anios = _contexto_filtros()
    areas_disponibles = _safe(coinin_cero_repository.get_areas_disponibles) or []
    orden = _ordenar_areas(areas_disponibles)
    area_actual = area if area in orden else (orden[0] if orden else None)
    tabs = [
        {
            "area": a,
            "label": _etiqueta_area(a),
            "url": _url_pestana(a, filtros),
            "activo": a == area_actual,
        }
        for a in orden
    ]
    grupo = _grupo_area(area_actual, anio, mes, nombre) if area_actual else None
    return render_template(
        "coinin_cero/detalle.html",
        user=current_user(),
        active="coinin_cero",
        seccion="detalle",
        titulo="Detalle",
        resumen=_safe(coinin_cero_repository.get_resumen, anio, mes, nombre, area_actual),
        tabs=tabs,
        grupo=grupo,
        sin_cruce=_safe(coinin_cero_repository.get_sin_cruce, anio, mes, nombre, area_actual),
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
