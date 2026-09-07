"""Módulo Análisis general — Comps vs Coin In por área de juego.

Dos niveles de navegación:
  Nivel 1 (área):   MDA (máquinas) | MDJ (mesas). NUNCA se mezclan: cada área
                    tiene su propia fuente de juego y su propio ratio.
  Nivel 2 (vista):  Comps vs Coin In | Preferencias de productos.

La cortesía se atribuye al área por la jefatura que la entregó
(comps.usuario_id -> jefaturas.area), así que un área sin jefaturas
configuradas no mostrará datos aunque haya cortesías cargadas.
"""
from datetime import datetime

from flask import Blueprint, redirect, render_template, request, url_for

from core.auth import current_user, login_required
from repositories import analisis_repository

analisis_bp = Blueprint("analisis", __name__, url_prefix="/analisis")

MESES = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]


def _safe(func, *args, **kwargs):
    """Ejecuta una consulta degradando a None ante cualquier error.

    Si una tabla del cruce aún no existe o no hay datos, la vista muestra el
    estado vacío en lugar de romperse.
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


def _tabs(area_actual, seccion, filtros):
    """Pestañas de área (MDA | MDJ) preservando los filtros activos."""
    args = {}
    if filtros["anio"]:
        args["anio"] = filtros["anio"]
    if filtros["mes"]:
        args["mes"] = filtros["mes"]
    if filtros["nombre"]:
        args["nombre"] = filtros["nombre"]

    endpoint = "analisis.productos" if seccion == "productos" else "analisis.comparativa"
    return [
        {
            "area": clave,
            "label": etiqueta,
            "url": url_for(endpoint, area=clave.lower(), **args),
            "activo": clave == area_actual,
        }
        for clave, etiqueta in analisis_repository.AREAS
    ]


def _resolver_area(area):
    """Normaliza el área de la URL; cae a MDA si no es válida."""
    clave = (area or "").upper()
    validas = [a for a, _ in analisis_repository.AREAS]
    return clave if clave in validas else validas[0]


@analisis_bp.route("/")
@login_required
def index():
    return redirect(url_for("analisis.comparativa", area="mda"))


@analisis_bp.route("/<area>")
@login_required
def comparativa(area):
    """Comps vs Coin In del área: cuánto se devuelve por cada peso jugado."""
    clave = _resolver_area(area)
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    return render_template(
        "analisis/comparativa.html",
        user=current_user(),
        active="analisis",
        area=clave,
        seccion="comparativa",
        tabs=_tabs(clave, "comparativa", filtros),
        resumen=_safe(analisis_repository.get_resumen, clave, anio, mes, nombre),
        kpis=_safe(analisis_repository.get_kpis, clave, anio, mes, nombre),
        comparativa=_safe(
            analisis_repository.get_comparativa_por_mes, clave, anio, mes, nombre
        ),
        top_clientes=_safe(
            analisis_repository.get_top_clientes, clave, anio, mes, nombre
        ),
        categorias=_safe(analisis_repository.get_categorias, clave, anio, mes, nombre),
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )


@analisis_bp.route("/<area>/productos")
@login_required
def productos(area):
    """Preferencias de producto por cliente dentro del área."""
    clave = _resolver_area(area)
    anio, mes, nombre, filtros, anios = _contexto_filtros()
    return render_template(
        "analisis/productos.html",
        user=current_user(),
        active="analisis",
        area=clave,
        seccion="productos",
        tabs=_tabs(clave, "productos", filtros),
        resumen=_safe(analisis_repository.get_resumen, clave, anio, mes, nombre),
        preferencias=_safe(
            analisis_repository.get_preferencias, clave, anio, mes, nombre
        ),
        productos_resumen=_safe(
            analisis_repository.get_productos_resumen, clave, anio, mes, nombre
        ),
        top_productos=_safe(
            analisis_repository.get_top_productos, clave, anio, mes, nombre
        ),
        categorias=_safe(analisis_repository.get_categorias, clave, anio, mes, nombre),
        filtros=filtros,
        anios=anios,
        meses=MESES,
    )
