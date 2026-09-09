"""Repositorio del módulo Coin In Cero (cruce entre comps, coinin y premios).

No tiene tabla propia: cruza tres módulos ya cargados para responder una sola
pregunta de negocio:

    ¿Quién recibió cortesías (comps) y NO jugó esa jornada (Coin In cero),
    qué jefe se las entregó y si además cobró un premio ese mismo día?

Llaves del cruce (verificadas contra la base):
- `comps.cliente_id` == `coinin.player_id` (mismo número de tarjeta del jugador).
- `premios.cliente` viene envuelto en "x" ('x30172...x'), por eso se limpia con
  TRIM(BOTH 'x' FROM cliente) antes de comparar.
- La jornada es un DATE en las tres tablas (regla 10:00 AM → 09:00 AM), así que
  se cruza directo: comps.fecha_jornada == coinin.jornada == premios.jornada.

Definición de "Coin In cero": un par (jugador, jornada) con cortesías quemadas
donde el Coin In de esa jornada es 0 **o no existe fila en `coinin`** (el
reporte diario solo trae a quien jugó, así que la ausencia también es cero).

La unidad de medida del módulo es el **caso** = un jugador en una jornada.
"""
from core.database import get_connection
from core.formato import fecha_corta, fecha_larga, mes_anio_es, mes_ingles, miles, pesos

# Colores del donut de áreas (consistentes con DESIGN.md).
_COLORES_AREA = [
    "#d4af37", "#24a148", "#78a9ff", "#ff832b",
    "#be95ff", "#08bdba", "#fa4d56", "#a56eff",
]

# Un cliente_id solo sirve para cruzar si es el número de tarjeta completo.
_ID_VALIDO = "c.cliente_id ~ '^[0-9]+$'"


# Expresión repetida en varias consultas: el área efectiva de una cortesía.
# Sin jefe (columna `nombre` vacía) se atribuye a la máquina de auto atención.
_AREA_EFECTIVA = (
    "CASE WHEN NULLIF(TRIM(c.nombre), '') IS NULL THEN 'Auto atención' "
    "ELSE COALESCE(NULLIF(TRIM(j.area), ''), 'Sin área') END"
)


def _cte(anio=None, mes=None, nombre=None, area=None):
    """Arma el CTE base y devuelve (sql, params).

    Deja disponibles dos vistas temporales para las consultas que siguen:

    - `comps_j`: una fila por jugador-jornada-jefe con cortesías entregadas.
    - `cero`:    lo mismo, pero solo los casos sin juego, ya cruzados con premios.

    Los filtros de año/mes se aplican a las TRES tablas (si se filtrara solo
    comps, el cruce con coinin/premios leería todo el histórico sin necesidad).
    El filtro de nombre aplica solo a comps (jugador o jefe), porque es el
    universo que define los casos. El filtro de área divide el módulo por la
    jefatura que entregó la cortesía (o "Auto atención" si no tuvo jefe).
    """
    f_comps, p_comps = [], []
    f_fecha, p_fecha = [], []

    if anio:
        f_comps.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        p_comps.append(int(anio))
        f_fecha.append("EXTRACT(YEAR FROM jornada) = %s")
        p_fecha.append(int(anio))
    if mes:
        f_comps.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        p_comps.append(int(mes))
        f_fecha.append("EXTRACT(MONTH FROM jornada) = %s")
        p_fecha.append(int(mes))
    if nombre:
        f_comps.append("(c.nombre_cliente ILIKE %s OR c.nombre ILIKE %s)")
        p_comps.append(f"%{nombre}%")
        p_comps.append(f"%{nombre}%")
    if area:
        f_comps.append(f"({_AREA_EFECTIVA}) = %s")
        p_comps.append(area)

    # Solo cruzan las cortesías con un cliente_id numérico válido. Ver
    # get_sin_cruce(): las cargas antiguas de COMPS guardaron algunos ID en
    # notación científica ('3.0172e+20') y con ese valor es imposible saber si
    # el jugador jugó. Contarlos como "no jugó" inflaría el módulo.
    f_comps.append(_ID_VALIDO)

    where_comps = "WHERE " + " AND ".join(f_comps)
    where_fecha = ("WHERE " + " AND ".join(f_fecha)) if f_fecha else ""

    sql = f"""
        WITH comps_j AS (
            SELECT c.fecha_jornada                                          AS jornada,
                   TRIM(c.cliente_id)                                       AS cliente_id,
                   COALESCE(NULLIF(TRIM(c.nombre_cliente), ''), 'Sin nombre') AS jugador,
                   NULLIF(TRIM(c.nombre), '')                               AS jefe,
                   NULLIF(TRIM(j.area), '')                                 AS area,
                   COALESCE(NULLIF(TRIM(c.descripcion_prod), ''), 'Sin especificar') AS producto,
                   COUNT(*)                                                 AS cortesias,
                   COALESCE(SUM(c.micros), 0)                               AS monto
            FROM comps c
            LEFT JOIN jefaturas j ON j.usuario_id = c.usuario_id
            {where_comps}
            GROUP BY 1, 2, 3, 4, 5, 6
        ),
        jugado AS (
            -- Se considera "jugó" tanto en máquinas (coinin: MDA/MDJ) como en
            -- mesas (coin_in = PUNTOS_OBTENIDOS x 1000, seudo Coin In).
            SELECT jornada, player_id, SUM(coin_in) AS coin_in
            FROM (
                SELECT jornada, player_id, coin_in FROM coinin
                UNION ALL
                SELECT fecha_operacion AS jornada, id_cliente AS player_id, coin_in
                FROM mesas
            ) todo
            {where_fecha}
            GROUP BY 1, 2
        ),
        premiado AS (
            SELECT jornada,
                   TRIM(BOTH 'x' FROM cliente)      AS cliente_id,
                   COUNT(*)                         AS premios,
                   COALESCE(SUM(transferencia_final), 0) AS monto_premio
            FROM premios
            {where_fecha}
            GROUP BY 1, 2
        ),
        cero AS (
            SELECT cj.jornada, cj.cliente_id, cj.jugador, cj.jefe, cj.area, cj.producto,
                   cj.cortesias, cj.monto,
                   COALESCE(pr.premios, 0)      AS premios,
                   COALESCE(pr.monto_premio, 0) AS monto_premio
            FROM comps_j cj
            LEFT JOIN jugado ju
                   ON ju.player_id = cj.cliente_id AND ju.jornada = cj.jornada
            LEFT JOIN premiado pr
                   ON pr.cliente_id = cj.cliente_id AND pr.jornada = cj.jornada
            WHERE COALESCE(ju.coin_in, 0) = 0
        )
    """
    # El orden de los parámetros sigue el orden de los CTE: comps, jugado, premiado.
    return sql, p_comps + p_fecha + p_fecha


def get_sin_cruce(anio=None, mes=None, nombre=None, area=None):
    """Cortesías del filtro que NO se pueden cruzar por tener un ID inválido.

    Algunas cargas de COMPS guardaron el "Cliente Id" en notación científica
    ('3.0172e+20') porque el Excel lo entregó como número y se perdieron
    dígitos. Esas filas quedan fuera del análisis (no se puede saber si el
    jugador jugó) y la vista muestra el aviso para que se vuelvan a cargar.

    Devuelve None si está todo sano, o un dict con el detalle del problema.
    """
    filtros, params = [f"NOT ({_ID_VALIDO})"], []
    if anio:
        filtros.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(c.nombre_cliente ILIKE %s OR c.nombre ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")
    if area:
        filtros.append(f"({_AREA_EFECTIVA}) = %s")
        params.append(area)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)                 AS cortesias,
                       COALESCE(SUM(c.micros), 0) AS monto,
                       MIN(c.fecha_jornada)     AS desde,
                       MAX(c.fecha_jornada)     AS hasta
                FROM comps c
                LEFT JOIN jefaturas j ON j.usuario_id = c.usuario_id
                WHERE {" AND ".join(filtros)}
                """,
                params,
            )
            r = cur.fetchone() or {}
    finally:
        conn.close()

    cortesias = int(r.get("cortesias") or 0)
    if not cortesias:
        return None
    return {
        "cortesias": miles(cortesias),
        "monto": pesos(r.get("monto")),
        "desde": fecha_corta(r.get("desde")),
        "hasta": fecha_corta(r.get("hasta")),
    }


def get_resumen(anio=None, mes=None, nombre=None, area=None):
    """Tarjetas de resumen del header. None si el filtro no arroja casos."""
    cte, params = _cte(anio, mes, nombre, area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT MAX(jornada)                          AS max_jornada,
                       COUNT(DISTINCT (jornada, cliente_id)) AS casos,
                       SUM(monto)                            AS monto
                FROM cero
                """,
                params,
            )
            r = cur.fetchone()
            if not r or not r["casos"]:
                return None
            return {
                "mes_cargado": mes_ingles(r["max_jornada"]),
                "hasta_jornada": fecha_larga(r["max_jornada"]),
                "total_label_titulo": (
                    "Casos del mes" if mes else "Casos acumulados"
                ),
                "total_valor": miles(r["casos"]),
                "total_label": f"{pesos(r['monto'])} en cortesías",
            }
    finally:
        conn.close()


def get_kpis_dashboard(anio=None, mes=None, nombre=None, area=None):
    """Cuatro KPIs del dashboard de Coin In Cero.

    1. Casos sin juego (jugador-jornada) y su peso sobre el total de entregas.
    2. Monto en cortesías que no generó juego.
    3. Jugadores distintos involucrados y jornadas afectadas.
    4. Casos que además cobraron premio ese mismo día, con su monto.
    """
    cte, params = _cte(anio, mes, nombre, area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT COUNT(DISTINCT (jornada, cliente_id)) AS casos,
                       COUNT(DISTINCT cliente_id)            AS jugadores,
                       COUNT(DISTINCT jornada)               AS jornadas,
                       SUM(cortesias)                        AS cortesias,
                       SUM(monto)                            AS monto
                FROM cero
                """,
                params,
            )
            base = cur.fetchone() or {}

            # El premio es del par (jornada, jugador): se deduplica antes de sumar
            # porque en `cero` se repite por cada jefe que entregó cortesías.
            cur.execute(
                f"""
                {cte}
                SELECT COUNT(*)                          AS casos,
                       COALESCE(SUM(monto_premio), 0)    AS monto
                FROM (
                    SELECT DISTINCT jornada, cliente_id, monto_premio
                    FROM cero
                    WHERE premios > 0
                ) t
                """,
                params,
            )
            prem = cur.fetchone() or {}

            # Universo de comparación: todas las entregas del filtro, jugaran o no.
            cur.execute(
                f"""
                {cte}
                SELECT COUNT(*) AS casos, COALESCE(SUM(monto), 0) AS monto
                FROM (
                    SELECT jornada, cliente_id, SUM(monto) AS monto
                    FROM comps_j GROUP BY 1, 2
                ) t
                """,
                params,
            )
            total = cur.fetchone() or {}
    finally:
        conn.close()

    casos = int(base.get("casos") or 0)
    if not casos:
        return None

    monto = int(base.get("monto") or 0)
    cortesias = int(base.get("cortesias") or 0)
    jugadores = int(base.get("jugadores") or 0)
    jornadas = int(base.get("jornadas") or 0)
    casos_premio = int(prem.get("casos") or 0)
    monto_premio = int(prem.get("monto") or 0)
    casos_total = int(total.get("casos") or 0)
    monto_total = int(total.get("monto") or 0)

    pct_casos = round(casos * 100.0 / casos_total, 1) if casos_total else 0.0
    pct_monto = round(monto * 100.0 / monto_total, 1) if monto_total else 0.0
    pct_premio = round(casos_premio * 100.0 / casos, 1) if casos else 0.0

    return {
        "casos": miles(casos),
        "pct_casos": f"{pct_casos}%",
        "casos_total": miles(casos_total),
        "monto": pesos(monto),
        "pct_monto": f"{pct_monto}%",
        "monto_caso": pesos(round(monto / casos)),
        "cortesias": miles(cortesias),
        "jugadores": miles(jugadores),
        "jornadas": miles(jornadas),
        "casos_jornada": miles(round(casos / jornadas)) if jornadas else "0",
        "casos_premio": miles(casos_premio),
        "pct_premio": f"{pct_premio}%",
        "monto_premio": pesos(monto_premio),
    }


def get_casos_por_mes(anio=None, mes=None, nombre=None, area=None):
    """Casos y monto de cortesías sin juego, agrupados por mes de la jornada."""
    cte, params = _cte(anio, mes, nombre, area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT DATE_TRUNC('month', jornada)          AS mes,
                       COUNT(DISTINCT (jornada, cliente_id)) AS casos,
                       SUM(monto)                            AS monto
                FROM cero
                GROUP BY 1
                ORDER BY 1
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None
    return {
        "labels": [mes_anio_es(f["mes"]) for f in filas],
        "casos": [int(f["casos"] or 0) for f in filas],
        "montos": [int(f["monto"] or 0) for f in filas],
    }


def get_areas(anio=None, mes=None, nombre=None, area=None):
    """Distribución de las cortesías sin juego por área de la jefatura (donut)."""
    cte, params = _cte(anio, mes, nombre, area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT CASE WHEN jefe IS NULL THEN 'Auto atención'
                            ELSE COALESCE(area, 'Sin área') END AS area,
                       COUNT(DISTINCT (jornada, cliente_id))    AS casos,
                       SUM(monto)                               AS monto
                FROM cero
                GROUP BY 1
                ORDER BY 3 DESC
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    total = sum(int(f["monto"] or 0) for f in filas) or 1
    return [
        {
            "label": f["area"],
            "casos": int(f["casos"] or 0),
            "monto": int(f["monto"] or 0),
            "pct": round(int(f["monto"] or 0) * 100.0 / total, 1),
            "color": _COLORES_AREA[i % len(_COLORES_AREA)],
        }
        for i, f in enumerate(filas)
    ]


def get_areas_disponibles():
    """Lista de áreas para poblar el filtro (incluye Auto atención/Sin área)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT {_AREA_EFECTIVA} AS area
                FROM comps c
                LEFT JOIN jefaturas j ON j.usuario_id = c.usuario_id
                WHERE {_ID_VALIDO}
                ORDER BY 1
                """
            )
            return [r["area"] for r in cur.fetchall()]
    finally:
        conn.close()


def get_ranking_jefes(anio=None, mes=None, nombre=None, area=None, limit=15):
    """Ranking de jefes por cortesías entregadas a jugadores que no jugaron.

    Cuando la cortesía no tiene jefe (columna `nombre` vacía en comps) se trata
    de una máquina de auto atención, igual que en el módulo Comps.
    """
    cte, params = _cte(anio, mes, nombre, area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT COALESCE(jefe, 'Auto atención')                       AS jefe,
                       CASE WHEN jefe IS NULL THEN 'Máquina'
                            ELSE COALESCE(area, 'Sin área') END              AS area,
                       COUNT(DISTINCT (jornada, cliente_id))                 AS casos,
                       COUNT(DISTINCT cliente_id)                            AS jugadores,
                       SUM(cortesias)                                        AS cortesias,
                       SUM(monto)                                            AS monto,
                       COUNT(DISTINCT (jornada, cliente_id))
                           FILTER (WHERE premios > 0)                        AS con_premio
                FROM cero
                GROUP BY 1, 2
                ORDER BY 6 DESC
                LIMIT %s
                """,
                params + [limit],
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None
    return [
        {
            "jefe": f["jefe"],
            "area": f["area"],
            "casos": int(f["casos"] or 0),
            "casos_fmt": miles(f["casos"]),
            "jugadores_fmt": miles(f["jugadores"]),
            "cortesias_fmt": miles(f["cortesias"]),
            "monto": int(f["monto"] or 0),
            "monto_fmt": pesos(f["monto"]),
            "con_premio_fmt": miles(f["con_premio"]),
        }
        for f in filas
    ]


def get_detalle(anio=None, mes=None, nombre=None, area=None):
    """Detalle expandible: jugador → jornadas en las que recibió comps sin jugar.

    Cada jornada trae los jefes que entregaron (con su área y el producto
    entregado) y el premio que el jugador cobró ese mismo día, si lo hubo.

    Devuelve una lista ordenada por monto de cortesías descendente:
        [{jugador, cliente_id, jornadas_n, cortesias, monto, monto_premio,
          jornadas: [{fecha, cortesias, monto, jefes, premio, ...}]}, ...]
    """
    cte, params = _cte(anio, mes, nombre, area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT jornada, cliente_id, jugador, jefe, area, producto,
                       cortesias, monto, premios, monto_premio
                FROM cero
                ORDER BY jugador, jornada DESC
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    jugadores = {}
    for f in filas:
        cid = f["cliente_id"]
        jug = jugadores.setdefault(
            cid,
            {
                # Algunas cortesías vienen sin nombre; mostramos la tarjeta para
                # que la fila siga siendo identificable.
                "jugador": (
                    f["jugador"] if f["jugador"] != "Sin nombre" else f"Tarjeta {cid}"
                ),
                "cliente_id": cid,
                "cortesias": 0,
                "monto": 0,
                "monto_premio": 0,
                "con_premio": 0,
                "_jornadas": {},
            },
        )
        clave = f["jornada"]
        jor = jug["_jornadas"].get(clave)
        if jor is None:
            # El premio pertenece al par (jugador, jornada): se suma una sola vez,
            # aunque el par aparezca repetido por cada jefe que entregó cortesías.
            jor = {
                "jornada": clave,
                "fecha": fecha_corta(clave),
                "cortesias": 0,
                "monto": 0,
                "premios": int(f["premios"] or 0),
                "monto_premio": int(f["monto_premio"] or 0),
                "jefes": [],
            }
            jug["_jornadas"][clave] = jor
            jug["monto_premio"] += jor["monto_premio"]
            if jor["premios"]:
                jug["con_premio"] += 1

        cantidad = int(f["cortesias"] or 0)
        monto = int(f["monto"] or 0)
        jor["cortesias"] += cantidad
        jor["monto"] += monto
        jug["cortesias"] += cantidad
        jug["monto"] += monto

        es_maquina = not f["jefe"]
        jor["jefes"].append(
            {
                "jefe": "Auto atención" if es_maquina else f["jefe"],
                "area": "Máquina" if es_maquina else (f["area"] or "Sin área"),
                "producto": f["producto"] or "Sin especificar",
                "cantidad": cantidad,
                "monto": monto,
            }
        )

    salida = []
    for jug in jugadores.values():
        jornadas = sorted(
            jug.pop("_jornadas").values(), key=lambda j: j["jornada"], reverse=True
        )
        for j in jornadas:
            j["jefes"].sort(key=lambda x: x["monto"], reverse=True)
            j["cortesias_fmt"] = miles(j["cortesias"])
            j["monto_fmt"] = pesos(j["monto"])
            j["premio_fmt"] = pesos(j["monto_premio"]) if j["premios"] else "—"
        jug["jornadas"] = jornadas
        jug["jornadas_n"] = len(jornadas)
        jug["cortesias_fmt"] = miles(jug["cortesias"])
        jug["monto_fmt"] = pesos(jug["monto"])
        jug["premio_fmt"] = pesos(jug["monto_premio"]) if jug["con_premio"] else "—"
        salida.append(jug)

    salida.sort(key=lambda j: j["monto"], reverse=True)
    return salida


def get_coin_in_periodo(area, anio, mes, cliente_ids):
    """Coin In real (jornadas jugadas) y categoría de cada jugador en el periodo.

    Se usa para el "Monto disponible": el jugador tuvo Coin In cero justo en
    los casos de este módulo, pero puede haber jugado otros días del mismo
    periodo (año/mes filtrado) — ese es el Coin In que se multiplica por los
    porcentajes de Configuración. Solo existe fuente para MDA (tabla `coinin`)
    y MDJ (tabla `mesas`); cualquier otra área devuelve {}.

    Devuelve {cliente_id: {"coin_in": int, "categoria": str|None}}.
    """
    if area not in ("MDA", "MDJ") or not cliente_ids:
        return {}

    if area == "MDA":
        tabla_sql = """
            SELECT player_id AS cliente_id,
                   SUM(coin_in) AS coin_in,
                   MAX(player_level) AS categoria
            FROM coinin
            WHERE sistema = 'MDA' AND player_id = ANY(%s)
        """
        campo_fecha = "jornada"
    else:
        tabla_sql = """
            SELECT id_cliente AS cliente_id,
                   SUM(coin_in) AS coin_in,
                   MAX(categoria) AS categoria
            FROM mesas
            WHERE id_cliente = ANY(%s)
        """
        campo_fecha = "fecha_operacion"

    params = [list(cliente_ids)]
    if anio:
        tabla_sql += f" AND EXTRACT(YEAR FROM {campo_fecha}) = %s"
        params.append(int(anio))
    if mes:
        tabla_sql += f" AND EXTRACT(MONTH FROM {campo_fecha}) = %s"
        params.append(int(mes))
    tabla_sql += " GROUP BY 1"

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(tabla_sql, params)
            filas = cur.fetchall()
    finally:
        conn.close()

    return {
        f["cliente_id"]: {"coin_in": int(f["coin_in"] or 0), "categoria": f["categoria"]}
        for f in filas
    }
