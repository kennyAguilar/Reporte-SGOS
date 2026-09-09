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
from repositories import coinin_cero_repository, config_repository

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

# "Monto disponible" (Coin In × Primario × % Categoría) solo tiene fuente de
# Coin In real para estas dos áreas (tablas coinin/mesas). Variantes de
# categoría que llegan sin el prefijo "DREAMS" desde los Excel de origen.
_AREAS_CON_COIN_IN = ("MDA", "MDJ")
_ALIAS_CATEGORIA = {
    "BLACK": "DREAMS BLACK",
    "GOLD": "DREAMS GOLD",
    "PLATINUM": "DREAMS PLATINUM",
}


def _normalizar_categoria(categoria):
    """Homologa variantes de categoría a las claves de categorias_margen."""
    cat = (categoria or "").strip().upper()
    return _ALIAS_CATEGORIA.get(cat, cat)


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
    """Arma el grupo del Detalle para un área: sus jefes + resumen."""
    jefes = _safe(coinin_cero_repository.get_detalle, anio, mes, nombre, area)
    if jefes and area in _AREAS_CON_COIN_IN:
        _agregar_monto_disponible(jefes, area, anio, mes)
    resumen = None
    if jefes:
        # "Caso" sigue siendo (jugador, jornada); como ahora se agrupa por
        # jefe, un mismo caso puede repartirse entre varios jefes distintos
        # el mismo día, así que se cuenta con un set en vez de sumar jornadas_n.
        casos = set()
        clientes = set()
        monto = 0
        for jef in jefes:
            monto += jef["monto"]
            for jor in jef["jornadas"]:
                for jug in jor["jugadores"]:
                    casos.add((jug["cliente_id"], jor["jornada"]))
                    clientes.add(jug["cliente_id"])
        resumen = {
            "jugadores": miles(len(clientes)),
            "casos": miles(len(casos)),
            "monto": pesos(monto),
        }
    return {
        "area": area,
        "label": _etiqueta_area(area),
        "jefes": jefes,
        "resumen": resumen,
        "con_monto_disponible": area in _AREAS_CON_COIN_IN,
    }


def _agregar_monto_disponible(jefes, area, anio, mes):
    """Calcula "Monto disponible para invitaciones" agregado por jefe.

    Fórmula pedida por el usuario, en dos pasos, POR JUGADOR:
      1) Teórico   = Coin In del jugador en el periodo × % Primario.
      2) Disponible = Teórico × % de su categoría (DREAMS/GOLD/BLACK/PLATINUM).
    El Coin In es el real de sus jornadas JUGADAS del mismo periodo (aquí,
    por definición del módulo, es 0 en los casos listados). Categoría sin
    match en la tabla de Configuración -> disponible 0 (no se puede calcular).

    El total que se muestra en la fila del jefe es la SUMA del disponible de
    cada jugador DISTINTO que recibió cortesías de él (un jugador que aparece
    en varias jornadas del mismo jefe cuenta una sola vez, porque su Coin In
    y su disponible son del periodo completo, no de un día puntual).
    """
    categorias = _safe(config_repository.list_categorias_margen) or []
    pct_por_categoria = {c["categoria"].strip().upper(): float(c["porcentaje"]) for c in categorias}
    pct_primario = pct_por_categoria.get("PRIMARIO", 0.0)

    cliente_ids = sorted({cid for jef in jefes for cid in jef["cliente_ids"]})
    coin_in_map = _safe(
        coinin_cero_repository.get_coin_in_periodo, area, anio, mes, cliente_ids
    ) or {}

    disponible_por_cliente = {}
    for cid in cliente_ids:
        datos = coin_in_map.get(cid) or {"coin_in": 0, "categoria": None}
        coin_in = datos["coin_in"]
        categoria_norm = _normalizar_categoria(datos["categoria"])
        pct_categoria = pct_por_categoria.get(categoria_norm)
        teorico = coin_in * pct_primario / 100
        disponible = teorico * pct_categoria / 100 if pct_categoria is not None else 0
        disponible_por_cliente[cid] = {"coin_in": coin_in, "disponible": disponible}

    for jef in jefes:
        coin_in_total = sum(disponible_por_cliente[cid]["coin_in"] for cid in jef["cliente_ids"])
        disponible_total = sum(disponible_por_cliente[cid]["disponible"] for cid in jef["cliente_ids"])
        jef["coin_in_fmt"] = pesos(coin_in_total)
        jef["monto_disponible_fmt"] = pesos(disponible_total)


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
