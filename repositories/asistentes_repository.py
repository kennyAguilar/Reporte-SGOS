"""Repositorio del módulo Asistentes: rendimiento combinado Getnet + Premios.

Une las operaciones de las tablas `getnet` y `premios` por slot attendant y
jornada, y sobre ese total aplica el mismo modelo de evaluación que usan los
módulos individuales. Solo cuenta CANTIDAD de operaciones: los montos de uno y
otro módulo no son comparables, así que aquí no se suman ni se muestran.

Reglas:
  - Jornada trabajada = día en que el asistente tuvo al menos una operación en
    cualquiera de los dos módulos.
  - Jornadas del periodo = días con operaciones en cualquiera de los dos.
  - Se excluyen los asistentes inactivos de Configuración y las filas sin
    asistente. El filtro Nombre busca solo en `slot_attendant`.
  - Si alguna de las dos tablas aún no existe, se trabaja solo con la otra.
"""
from core.database import get_connection
from core.formato import fecha_corta, mes_anio_es, miles, porcentaje, variacion

# (clave, tabla). La clave se usa como etiqueta de origen en la unión.
_FUENTES = (("getnet", "getnet"), ("premios", "premios"))

_FILTRO_ACTIVOS = (
    "slot_attendant NOT IN "
    "(SELECT nombre FROM slot_attendants WHERE activo = false)"
)
_FILTRO_CON_ASISTENTE = "NULLIF(TRIM(slot_attendant), '') IS NOT NULL"

# Jornadas mínimas para entrar al ranking de promedio por jornada.
_MIN_JORNADAS_RANKING = 5


def _tablas_existentes(cur):
    """Devuelve las fuentes cuya tabla existe en la base."""
    existentes = []
    for clave, tabla in _FUENTES:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS existe", (f"public.{tabla}",))
        if (cur.fetchone() or {}).get("existe"):
            existentes.append((clave, tabla))
    return existentes


def _where(anio=None, mes=None, nombre=None):
    """WHERE común a ambas tablas (comparten `slot_attendant` y `jornada`)."""
    filtros, params = [], []
    if anio:
        filtros.append("EXTRACT(YEAR FROM jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("slot_attendant ILIKE %s")
        params.append(f"%{nombre}%")
    filtros.append(_FILTRO_ACTIVOS)
    filtros.append(_FILTRO_CON_ASISTENTE)
    return "WHERE " + " AND ".join(filtros), params


def _union(fuentes, where):
    """Subconsulta UNION ALL con (slot_attendant, jornada, origen)."""
    partes = [
        f"SELECT slot_attendant, jornada, '{clave}' AS origen FROM {tabla} {where}"
        for clave, tabla in fuentes
    ]
    return "(" + " UNION ALL ".join(partes) + ") u"


def get_anios_disponibles():
    """Años con operaciones en Getnet o Premios, de más reciente a más antiguo."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fuentes = _tablas_existentes(cur)
            if not fuentes:
                return []
            union = " UNION ".join(
                f"SELECT DISTINCT EXTRACT(YEAR FROM jornada)::int AS anio FROM {tabla}"
                for _, tabla in fuentes
            )
            cur.execute(f"SELECT DISTINCT anio FROM ({union}) a ORDER BY 1 DESC")
            return [int(f["anio"]) for f in cur.fetchall()]
    finally:
        conn.close()


def _mediana(valores):
    if not valores:
        return 0
    v = sorted(valores)
    n = len(v)
    mitad = n // 2
    return v[mitad] if n % 2 else (v[mitad - 1] + v[mitad]) / 2


def _fmt1(x):
    return f"{x:.1f}".replace(".", ",")


def get_rendimiento_combinado(anio=None, mes=None, nombre=None):
    """Evaluación de desempeño por asistente sumando Getnet + Premios.

    Una sola consulta devuelve, por (asistente, jornada), el total de
    operaciones y el desglose por origen; el resto se calcula en Python.

    Devuelve un dict con:
      - kpis:    asistentes, jornadas_periodo, prom_por_asistente, mediana,
                 prom_equipo, lider, lider_prom, top3_pct, top1, top1_pct,
                 total_ops, getnet_pct, premios_pct
      - podio:   [{nombre, ops, getnet, premios, fecha}] Top 3 mejor jornada combinada
      - filas:   lista ordenada por total desc (formateada + *_raw para gráficos)
      - totales: fila de pie
      - top_mix: {labels, getnet, premios} Top 10 por total (para barras apiladas)
      - top_prom:{labels, valores} Top 10 por prom./jornada (min. jornadas)
      - min_jornadas, tendencia ({mes_ref, mes_prev} o None)
      - fuentes: ["getnet", "premios"] tablas realmente consultadas
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fuentes = _tablas_existentes(cur)
            if not fuentes:
                return None
            union = _union(fuentes, where)
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre,
                       jornada,
                       COUNT(*) AS ops,
                       SUM(CASE WHEN origen = 'getnet'  THEN 1 ELSE 0 END) AS getnet,
                       SUM(CASE WHEN origen = 'premios' THEN 1 ELSE 0 END) AS premios
                FROM {union}
                GROUP BY slot_attendant, jornada
                """,
                params * len(fuentes),
            )
            filas_sql = cur.fetchall()
    finally:
        conn.close()

    if not filas_sql:
        return None

    # por_asistente[nombre] = [(jornada, ops, getnet, premios), ...]
    por_asistente = {}
    jornadas_periodo = set()
    for f in filas_sql:
        jornadas_periodo.add(f["jornada"])
        por_asistente.setdefault(f["nombre"], []).append(
            (f["jornada"], int(f["ops"]), int(f["getnet"] or 0), int(f["premios"] or 0))
        )
    n_jornadas_periodo = len(jornadas_periodo)

    total_ops = sum(j[1] for js in por_asistente.values() for j in js)
    total_getnet = sum(j[2] for js in por_asistente.values() for j in js)
    total_premios = sum(j[3] for js in por_asistente.values() for j in js)
    total_pares = sum(len(js) for js in por_asistente.values())
    prom_equipo = total_ops / total_pares if total_pares else 0

    meses = sorted({j[0].replace(day=1) for js in por_asistente.values() for j in js})
    mes_ref = meses[-1] if len(meses) >= 2 else None
    mes_prev = meses[-2] if len(meses) >= 2 else None

    filas = []
    for nom, js in por_asistente.items():
        ops = sum(j[1] for j in js)
        g = sum(j[2] for j in js)
        p = sum(j[3] for j in js)
        jornadas = len(js)
        prom = ops / jornadas if jornadas else 0
        indice = prom * 100 / prom_equipo if prom_equipo else 0
        # Mejor jornada: más ops; empate → la más reciente.
        mejor = max(js, key=lambda j: (j[1], j[0]))
        sobre_prom = sum(1 for j in js if j[1] >= prom_equipo)

        tendencia = None
        if mes_ref:
            por_mes = {}
            for j in js:
                m = j[0].replace(day=1)
                por_mes[m] = por_mes.get(m, 0) + j[1]
            tendencia = variacion(por_mes.get(mes_ref, 0), por_mes.get(mes_prev, 0))
            if tendencia is None and por_mes.get(mes_ref, 0) and not por_mes.get(mes_prev, 0):
                tendencia = {"pct": "nuevo", "dir": "flat"}

        filas.append(
            {
                "nombre": nom,
                "ops_raw": ops,
                "getnet_raw": g,
                "premios_raw": p,
                "prom_raw": round(prom, 1),
                "jornadas_raw": jornadas,
                "ops": miles(ops),
                "getnet": miles(g),
                "premios": miles(p),
                "getnet_pct": porcentaje(g, ops, 0),
                "pct_total": porcentaje(ops, total_ops),
                "jornadas": miles(jornadas),
                "cobertura": porcentaje(jornadas, n_jornadas_periodo, 0),
                "prom_jornada": _fmt1(prom),
                "indice": round(indice),
                "constancia": porcentaje(sobre_prom, jornadas, 0),
                "mejor_ops": mejor[1],
                "mejor_getnet": mejor[2],
                "mejor_premios": mejor[3],
                "mejor_fecha": fecha_corta(mejor[0]),
                "mejor_fecha_iso": mejor[0].isoformat(),
                "tendencia": tendencia,
            }
        )
    filas.sort(key=lambda r: (-r["ops_raw"], r["nombre"]))

    # Podio: mejor jornada combinada; empate → quien lo logró primero.
    podio = sorted(filas, key=lambda r: (-r["mejor_ops"], r["mejor_fecha_iso"], r["nombre"]))[:3]
    podio = [
        {
            "nombre": r["nombre"],
            "ops": r["mejor_ops"],
            "getnet": r["mejor_getnet"],
            "premios": r["mejor_premios"],
            "fecha": r["mejor_fecha"],
        }
        for r in podio
    ]

    n_asist = len(filas)
    ops_list = [f["ops_raw"] for f in filas]
    lider = max(filas, key=lambda r: (r["prom_raw"], r["ops_raw"]))

    min_jornadas = min(_MIN_JORNADAS_RANKING, n_jornadas_periodo) or 1
    elegibles = [f for f in filas if f["jornadas_raw"] >= min_jornadas]
    elegibles.sort(key=lambda r: (-r["prom_raw"], -r["ops_raw"], r["nombre"]))

    top = filas[:10]
    return {
        "kpis": {
            "asistentes": miles(n_asist),
            "jornadas_periodo": miles(n_jornadas_periodo),
            "prom_por_asistente": miles(round(total_ops / n_asist)) if n_asist else "0",
            "mediana": miles(round(_mediana(ops_list))),
            "prom_equipo": _fmt1(prom_equipo),
            "lider": lider["nombre"],
            "lider_prom": lider["prom_jornada"],
            "top3_pct": porcentaje(sum(ops_list[:3]), total_ops),
            "top1": filas[0]["nombre"],
            "top1_pct": filas[0]["pct_total"],
            "total_ops": miles(total_ops),
            "getnet_pct": porcentaje(total_getnet, total_ops, 0),
            "premios_pct": porcentaje(total_premios, total_ops, 0),
        },
        "podio": podio,
        "filas": filas,
        "totales": {
            "ops": miles(total_ops),
            "getnet": miles(total_getnet),
            "premios": miles(total_premios),
            "getnet_pct": porcentaje(total_getnet, total_ops, 0),
            "jornadas": miles(n_jornadas_periodo),
            "prom_jornada": _fmt1(prom_equipo),
        },
        "top_mix": {
            "labels": [f["nombre"] for f in top],
            "getnet": [f["getnet_raw"] for f in top],
            "premios": [f["premios_raw"] for f in top],
        },
        "top_prom": {
            "labels": [f["nombre"] for f in elegibles[:10]],
            "valores": [f["prom_raw"] for f in elegibles[:10]],
        },
        "min_jornadas": min_jornadas,
        "tendencia": (
            {"mes_ref": mes_anio_es(mes_ref), "mes_prev": mes_anio_es(mes_prev)}
            if mes_ref else None
        ),
        "fuentes": [clave for clave, _ in fuentes],
    }
