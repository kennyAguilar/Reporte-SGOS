"""Repositorio del módulo Análisis (cruce Comps vs Coin In por área de juego).

No tiene tabla propia: cruza las cortesías entregadas (`comps`) contra el
juego real de cada área para responder la pregunta de negocio:

    ¿Cuánto estamos devolviendo en cortesías por cada peso que el cliente
    juega, y en qué se lo gasta?

Las dos áreas NO se mezclan nunca: cada consulta recibe `area` y usa su
propia fuente de juego.

    MDA (Máquinas)  -> tabla `coinin`, sistema = 'MDA' (Coin In Amount real).
    MDJ (Mesas)     -> tabla `mesas`  (PUNTOS_OBTENIDOS x 1000, seudo Coin In).

La cortesía se atribuye a un área por la JEFATURA que la entregó
(`comps.usuario_id` -> `jefaturas.area`). Una cortesía sin jefatura conocida
no pertenece a ninguna área y queda fuera del análisis.

Llave del cruce jugador: `comps.cliente_id` == `coinin.player_id` ==
`mesas.id_cliente` (número de tarjeta).
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_anio_es, mes_ingles, miles, pesos

# Áreas soportadas y su etiqueta para la interfaz.
AREAS = [("MDA", "MDA · Máquinas"), ("MDJ", "MDJ · Mesas")]

# Ventaja teórica de la casa: del total jugado (Coin In) se asume que el casino
# retiene un 6,5%. Ese "teórico" es la ganancia esperada del periodo y es la
# base contra la que se mide el costo real de las cortesías (compararlas contra
# el Coin In bruto da porcentajes irrisorios que no dicen nada del negocio).
MARGEN_TEORICO = 0.065
MARGEN_TEORICO_PCT = "6,5%"

# Colores del donut de categorías (consistentes con DESIGN.md).
_COLORES = [
    "#d4af37", "#24a148", "#78a9ff", "#ff832b",
    "#be95ff", "#08bdba", "#fa4d56", "#a56eff",
]

# Un cliente_id solo sirve para cruzar si es el número de tarjeta completo.
# Las cargas antiguas de COMPS guardaron algunos ID en notación científica
# ('3.0172e+20') y con ese valor es imposible identificar al jugador.
_ID_VALIDO = "c.cliente_id ~ '^[0-9]+$'"


def _fuente_juego(area):
    """Devuelve el SELECT con el juego del área, ya normalizado.

    Columnas de salida: jornada, cliente_id, nombre, coin_in, juegos.
    MDA y MDJ viven en tablas distintas y NUNCA se combinan.
    """
    if area == "MDJ":
        # Mesas: una fila por sesión, coin_in ya es el seudo Coin In (puntos x1000).
        return """
            SELECT fecha_operacion AS jornada,
                   id_cliente      AS cliente_id,
                   nombre          AS nombre,
                   coin_in         AS coin_in,
                   1               AS juegos
            FROM mesas
        """, []
    # MDA: reporte agregado por jugador y jornada.
    return """
        SELECT jornada     AS jornada,
               player_id   AS cliente_id,
               full_name   AS nombre,
               coin_in     AS coin_in,
               total_games AS juegos
        FROM coinin
        WHERE sistema = 'MDA'
    """, []


def _cte(area, anio=None, mes=None, nombre=None):
    """Arma el CTE base del módulo y devuelve (sql, params).

    Deja disponibles dos vistas temporales, ambas por (jornada, cliente_id):

    - `comps_a`: cortesías entregadas por jefaturas del área.
    - `juego_a`: juego real registrado en el área.

    Los filtros de año/mes se aplican a las DOS fuentes (si se filtrara solo
    una, el ratio compararía periodos distintos). El filtro de nombre busca al
    jugador en ambas.
    """
    fuente, p_fuente = _fuente_juego(area)

    f_comps, p_comps = ["TRIM(j.area) = %s", _ID_VALIDO], [area]
    f_juego, p_juego = [], []

    if anio:
        f_comps.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        p_comps.append(int(anio))
        f_juego.append("EXTRACT(YEAR FROM jornada) = %s")
        p_juego.append(int(anio))
    if mes:
        f_comps.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        p_comps.append(int(mes))
        f_juego.append("EXTRACT(MONTH FROM jornada) = %s")
        p_juego.append(int(mes))
    if nombre:
        f_comps.append("(c.nombre_cliente ILIKE %s OR c.cliente_id ILIKE %s)")
        p_comps.append(f"%{nombre}%")
        p_comps.append(f"%{nombre}%")
        f_juego.append("(nombre ILIKE %s OR cliente_id ILIKE %s)")
        p_juego.append(f"%{nombre}%")
        p_juego.append(f"%{nombre}%")

    where_comps = "WHERE " + " AND ".join(f_comps)
    where_juego = ("WHERE " + " AND ".join(f_juego)) if f_juego else ""

    sql = f"""
        WITH comps_a AS (
            SELECT c.fecha_jornada    AS jornada,
                   TRIM(c.cliente_id) AS cliente_id,
                   COALESCE(NULLIF(TRIM(c.nombre_cliente), ''), 'Sin nombre') AS jugador,
                   COUNT(*)                   AS cortesias,
                   COALESCE(SUM(c.micros), 0) AS monto
            FROM comps c
            JOIN jefaturas j ON j.usuario_id = c.usuario_id
            {where_comps}
            GROUP BY 1, 2, 3
        ),
        juego_a AS (
            SELECT jornada,
                   cliente_id,
                   MAX(nombre)       AS jugador,
                   SUM(coin_in)      AS coin_in,
                   SUM(juegos)       AS juegos
            FROM ({fuente}) f
            {where_juego}
            GROUP BY 1, 2
        )
    """
    # El orden de los parámetros sigue el orden de los CTE: comps, juego.
    return sql, p_comps + p_fuente + p_juego


def get_areas_con_datos():
    """Áreas de jefatura que existen realmente, para avisar si falta configurar."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT TRIM(area) AS area FROM jefaturas "
                "WHERE NULLIF(TRIM(area), '') IS NOT NULL ORDER BY 1"
            )
            return [r["area"] for r in cur.fetchall()]
    finally:
        conn.close()


def get_ids_invalidos(area, anio=None, mes=None, nombre=None):
    """Cortesías del área con cliente_id inválido (notación científica).

    Devuelve None si no hay ninguna (el aviso de la vista solo se muestra
    cuando el problema realmente existe para el filtro actual).
    """
    filtros, params = ["TRIM(j.area) = %s", f"NOT ({_ID_VALIDO})"], [area]
    if anio:
        filtros.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(c.nombre_cliente ILIKE %s OR c.cliente_id ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS cortesias, COALESCE(SUM(c.micros), 0) AS monto
                FROM comps c
                JOIN jefaturas j ON j.usuario_id = c.usuario_id
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
    return {"cortesias": miles(cortesias), "monto": pesos(r.get("monto"))}


def get_resumen(area, anio=None, mes=None, nombre=None):
    """Tarjetas de resumen del header. None si el área no tiene datos."""
    cte, params = _cte(area, anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT (SELECT MAX(jornada) FROM juego_a)      AS max_jornada,
                       (SELECT SUM(coin_in) FROM juego_a)      AS coin_in,
                       (SELECT SUM(monto)   FROM comps_a)      AS comps,
                       (SELECT COUNT(*)     FROM juego_a)      AS filas
                """,
                params,
            )
            r = cur.fetchone()
            if not r or not r["filas"]:
                return None

            coin_in = int(r["coin_in"] or 0)
            comps = int(r["comps"] or 0)
            teorico = coin_in * MARGEN_TEORICO
            ratio = round(comps * 100.0 / teorico, 2) if teorico else 0.0
            return {
                "mes_cargado": mes_ingles(r["max_jornada"]),
                "hasta_jornada": fecha_larga(r["max_jornada"]),
                "total_label_titulo": "Coin In del mes" if mes else "Coin In acumulado",
                "total_valor": pesos(coin_in),
                "total_label": f"{pesos(comps)} en cortesías",
                "ultima_valor": f"{ratio}%",
                "ultima_label": f"Cortesías sobre teórico ({MARGEN_TEORICO_PCT})",
            }
    finally:
        conn.close()


def get_kpis(area, anio=None, mes=None, nombre=None):
    """KPIs del análisis Comps vs Coin In del área.

    1. Ganancia teórica = Coin In × 6,5% (lo que se espera ganar del juego).
    2. Cortesías / teórico: qué parte de esa ganancia esperada se devolvió.
    3. Coin In del área (lo que el cliente jugó) y su promedio por jornada.
    4. Cortesías entregadas (monto y cantidad).
    5. Cobertura: de los clientes que recibieron cortesías, cuántos jugaron.
    """
    cte, params = _cte(area, anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte}
                SELECT
                  (SELECT SUM(coin_in)               FROM juego_a) AS coin_in,
                  (SELECT COUNT(DISTINCT jornada)    FROM juego_a) AS jornadas,
                  (SELECT COUNT(DISTINCT cliente_id) FROM juego_a) AS jugadores,
                  (SELECT SUM(juegos)                FROM juego_a) AS juegos,
                  (SELECT SUM(monto)                 FROM comps_a) AS comps_monto,
                  (SELECT SUM(cortesias)             FROM comps_a) AS cortesias,
                  (SELECT COUNT(DISTINCT cliente_id) FROM comps_a) AS clientes_comps,
                  (SELECT COUNT(DISTINCT c.cliente_id)
                     FROM comps_a c
                     JOIN juego_a g ON g.cliente_id = c.cliente_id)  AS clientes_ambos
                """,
                params,
            )
            r = cur.fetchone() or {}
    finally:
        conn.close()

    coin_in = int(r.get("coin_in") or 0)
    jornadas = int(r.get("jornadas") or 0)
    if not coin_in and not int(r.get("comps_monto") or 0):
        return None

    jugadores = int(r.get("jugadores") or 0)
    juegos = int(r.get("juegos") or 0)
    comps_monto = int(r.get("comps_monto") or 0)
    cortesias = int(r.get("cortesias") or 0)
    clientes_comps = int(r.get("clientes_comps") or 0)
    clientes_ambos = int(r.get("clientes_ambos") or 0)

    ratio = round(comps_monto * 100.0 / coin_in, 2) if coin_in else 0.0
    teorico = coin_in * MARGEN_TEORICO
    ratio_teorico = round(comps_monto * 100.0 / teorico, 2) if teorico else 0.0
    cobertura = (
        round(clientes_ambos * 100.0 / clientes_comps, 1) if clientes_comps else 0.0
    )

    return {
        "coin_in": pesos(coin_in),
        "coin_in_dia": pesos(round(coin_in / jornadas)) if jornadas else pesos(0),
        "coin_in_jugador": pesos(round(coin_in / jugadores)) if jugadores else pesos(0),
        "jornadas": miles(jornadas),
        "jugadores": miles(jugadores),
        "juegos": miles(juegos),
        "comps": pesos(comps_monto),
        "cortesias": miles(cortesias),
        "comps_cliente": (
            pesos(round(comps_monto / clientes_comps)) if clientes_comps else pesos(0)
        ),
        "clientes_comps": miles(clientes_comps),
        "ratio": f"{ratio}%",
        "ratio_valor": ratio,
        "retorno": (
            pesos(round(coin_in / comps_monto)) if comps_monto else pesos(0)
        ),
        "margen_pct": MARGEN_TEORICO_PCT,
        "teorico": pesos(round(teorico)),
        "teorico_dia": pesos(round(teorico / jornadas)) if jornadas else pesos(0),
        "teorico_jugador": (
            pesos(round(teorico / jugadores)) if jugadores else pesos(0)
        ),
        "ratio_teorico": f"{ratio_teorico}%",
        "ratio_teorico_valor": ratio_teorico,
        "retorno_teorico": (
            pesos(round(teorico / comps_monto)) if comps_monto else pesos(0)
        ),
        "cobertura": f"{cobertura}%",
        "clientes_ambos": miles(clientes_ambos),
        "clientes_sin_juego": miles(clientes_comps - clientes_ambos),
    }


def get_comparativa_por_mes(area, anio=None, mes=None, nombre=None):
    """Coin In vs Cortesías por mes, con el ratio de cada mes.

    Devuelve {labels, coin_in, comps, teorico, ratio, ratio_teorico,
    meses_sin_juego} para los gráficos. `ratio` compara contra el Coin In bruto
    y `ratio_teorico` contra la ganancia esperada (Coin In × 6,5%), que es la
    lectura que se muestra en pantalla.
    `meses_sin_juego` lista los meses que tienen cortesías pero NO tienen juego
    cargado: ahí el ratio no se puede calcular (sale 0) y hay que avisarlo, o se
    lee como "ese mes no costó nada" cuando en realidad falta el Excel.
    """
    cte, params = _cte(area, anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte},
                meses AS (
                    SELECT DATE_TRUNC('month', jornada) AS mes,
                           SUM(coin_in)                 AS coin_in,
                           0                            AS comps
                    FROM juego_a GROUP BY 1
                    UNION ALL
                    SELECT DATE_TRUNC('month', jornada) AS mes,
                           0                            AS coin_in,
                           SUM(monto)                   AS comps
                    FROM comps_a GROUP BY 1
                )
                SELECT mes, SUM(coin_in) AS coin_in, SUM(comps) AS comps
                FROM meses
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

    labels, coin_in, comps, ratio, sin_juego = [], [], [], [], []
    teorico, ratio_teorico = [], []
    for f in filas:
        ci = int(f["coin_in"] or 0)
        co = int(f["comps"] or 0)
        te = ci * MARGEN_TEORICO
        etiqueta = mes_anio_es(f["mes"])
        labels.append(etiqueta)
        coin_in.append(ci)
        comps.append(co)
        teorico.append(round(te))
        ratio.append(round(co * 100.0 / ci, 2) if ci else 0.0)
        ratio_teorico.append(round(co * 100.0 / te, 2) if te else 0.0)
        if co and not ci:
            sin_juego.append(etiqueta)
    return {
        "labels": labels,
        "coin_in": coin_in,
        "comps": comps,
        "teorico": teorico,
        "ratio": ratio,
        "ratio_teorico": ratio_teorico,
        "meses_sin_juego": sin_juego,
    }


def get_top_clientes(area, anio=None, mes=None, nombre=None, limit=25):
    """Clientes del área ordenados por cortesías recibidas.

    Cruza lo que cada cliente jugó contra lo que recibió, para ver el ratio
    individual. Un ratio alto = mucha cortesía para poco juego.
    """
    cte, params = _cte(area, anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {cte},
                union_cli AS (
                    SELECT cliente_id, jugador, 0 AS coin_in, 0 AS juegos,
                           cortesias, monto, jornada
                    FROM comps_a
                    UNION ALL
                    SELECT cliente_id, jugador, coin_in, juegos,
                           0 AS cortesias, 0 AS monto, jornada
                    FROM juego_a
                )
                SELECT cliente_id,
                       MAX(jugador)            AS jugador,
                       SUM(coin_in)            AS coin_in,
                       SUM(cortesias)          AS cortesias,
                       SUM(monto)              AS comps,
                       COUNT(DISTINCT jornada) AS jornadas
                FROM union_cli
                GROUP BY cliente_id
                HAVING SUM(monto) > 0
                ORDER BY SUM(monto) DESC
                LIMIT %s
                """,
                params + [limit],
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    salida = []
    for f in filas:
        coin_in = int(f["coin_in"] or 0)
        comps = int(f["comps"] or 0)
        teorico = coin_in * MARGEN_TEORICO
        ratio = round(comps * 100.0 / coin_in, 1) if coin_in else None
        ratio_teorico = round(comps * 100.0 / teorico, 1) if teorico else None
        salida.append(
            {
                "cliente_id": f["cliente_id"],
                "jugador": f["jugador"] or f"Tarjeta {f['cliente_id']}",
                "coin_in": pesos(coin_in),
                "teorico": pesos(round(teorico)),
                "comps": pesos(comps),
                "cortesias": miles(f["cortesias"]),
                "jornadas": miles(f["jornadas"]),
                # Sin juego el ratio es infinito: se marca aparte para la vista.
                "ratio": f"{ratio}%" if ratio is not None else "Sin juego",
                "ratio_teorico": (
                    f"{ratio_teorico}%" if ratio_teorico is not None else "Sin juego"
                ),
                "sin_juego": coin_in == 0,
            }
        )
    return salida


def get_top_productos(area, anio=None, mes=None, nombre=None, limit=12):
    """Productos más entregados por las jefaturas del área (gráfico de barras)."""
    filas = _productos_area(area, anio, mes, nombre, limit)
    if not filas:
        return None
    return {
        "labels": [f["producto"] for f in filas],
        "valores": [int(f["cantidad"] or 0) for f in filas],
    }


def _productos_area(area, anio, mes, nombre, limit=None):
    """Consulta cruda de productos entregados en el área (uso interno)."""
    filtros, params = ["TRIM(j.area) = %s", _ID_VALIDO], [area]
    if anio:
        filtros.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(c.nombre_cliente ILIKE %s OR c.cliente_id ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")

    limite = "LIMIT %s" if limit else ""
    if limit:
        params = params + [limit]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(c.descripcion_prod), ''), 'Sin especificar') AS producto,
                       COALESCE(NULLIF(TRIM(c.descripcion_cat), ''), 'Sin categoría')    AS categoria,
                       COUNT(*)                   AS cantidad,
                       COALESCE(SUM(c.micros), 0) AS monto,
                       COUNT(DISTINCT c.cliente_id) AS clientes
                FROM comps c
                JOIN jefaturas j ON j.usuario_id = c.usuario_id
                WHERE {" AND ".join(filtros)}
                GROUP BY 1, 2
                ORDER BY 3 DESC
                {limite}
                """,
                params,
            )
            return cur.fetchall()
    finally:
        conn.close()


def get_categorias(area, anio=None, mes=None, nombre=None):
    """Distribución del gasto en cortesías por categoría de producto (donut)."""
    filtros, params = ["TRIM(j.area) = %s", _ID_VALIDO], [area]
    if anio:
        filtros.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(c.nombre_cliente ILIKE %s OR c.cliente_id ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(c.descripcion_cat), ''), 'Sin categoría') AS categoria,
                       COUNT(*)                   AS cantidad,
                       COALESCE(SUM(c.micros), 0) AS monto
                FROM comps c
                JOIN jefaturas j ON j.usuario_id = c.usuario_id
                WHERE {" AND ".join(filtros)}
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
            "label": f["categoria"],
            "valor": int(f["monto"] or 0),
            "cantidad": int(f["cantidad"] or 0),
            "pct": round(int(f["monto"] or 0) * 100.0 / total, 1),
            "color": _COLORES[i % len(_COLORES)],
        }
        for i, f in enumerate(filas)
    ]


def get_preferencias(area, anio=None, mes=None, nombre=None, limit=60):
    """Preferencias de producto por cliente (tabla expandible).

    Una fila por cliente con su producto favorito y el detalle de todo lo que
    consumió, ordenado por gasto. Responde "¿qué le gusta a cada cliente?".

    Devuelve [{cliente_id, jugador, cortesias, monto, favorito,
               productos: [{producto, categoria, cantidad, monto, pct}]}]
    """
    filtros, params = ["TRIM(j.area) = %s", _ID_VALIDO], [area]
    if anio:
        filtros.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(c.nombre_cliente ILIKE %s OR c.cliente_id ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Se limita por CLIENTE (no por fila) para no cortar el detalle de
            # un cliente a la mitad: primero los que más gastaron.
            cur.execute(
                f"""
                WITH base AS (
                    SELECT TRIM(c.cliente_id) AS cliente_id,
                           COALESCE(NULLIF(TRIM(c.nombre_cliente), ''), 'Sin nombre') AS jugador,
                           COALESCE(NULLIF(TRIM(c.descripcion_prod), ''), 'Sin especificar') AS producto,
                           COALESCE(NULLIF(TRIM(c.descripcion_cat), ''), 'Sin categoría')    AS categoria,
                           c.micros AS micros
                    FROM comps c
                    JOIN jefaturas j ON j.usuario_id = c.usuario_id
                    WHERE {" AND ".join(filtros)}
                ),
                top_clientes AS (
                    SELECT cliente_id
                    FROM base
                    GROUP BY 1
                    ORDER BY COALESCE(SUM(micros), 0) DESC
                    LIMIT %s
                )
                SELECT b.cliente_id,
                       MAX(b.jugador)             AS jugador,
                       b.producto,
                       MAX(b.categoria)           AS categoria,
                       COUNT(*)                   AS cantidad,
                       COALESCE(SUM(b.micros), 0) AS monto
                FROM base b
                JOIN top_clientes t ON t.cliente_id = b.cliente_id
                GROUP BY b.cliente_id, b.producto
                ORDER BY 6 DESC
                """,
                params + [limit],
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    clientes = {}
    for f in filas:
        cid = f["cliente_id"]
        cli = clientes.setdefault(
            cid,
            {
                "cliente_id": cid,
                # Algunas cortesías vienen sin nombre; mostramos la tarjeta
                # para que la fila siga siendo identificable.
                "jugador": (
                    f["jugador"] if f["jugador"] != "Sin nombre" else f"Tarjeta {cid}"
                ),
                "cortesias": 0,
                "monto": 0,
                "productos": [],
            },
        )
        cantidad = int(f["cantidad"] or 0)
        monto = int(f["monto"] or 0)
        cli["cortesias"] += cantidad
        cli["monto"] += monto
        cli["productos"].append(
            {
                "producto": f["producto"],
                "categoria": f["categoria"],
                "cantidad": cantidad,
                "monto": monto,
            }
        )

    salida = []
    for cli in clientes.values():
        cli["productos"].sort(key=lambda p: p["monto"], reverse=True)
        total = cli["monto"] or 1
        for p in cli["productos"]:
            p["pct"] = round(p["monto"] * 100.0 / total, 1)
            p["cantidad_fmt"] = miles(p["cantidad"])
            p["monto_fmt"] = pesos(p["monto"])
        favorito = cli["productos"][0]
        salida.append(
            {
                **cli,
                "favorito": favorito["producto"],
                "favorito_pct": f"{favorito['pct']}%",
                "productos_n": len(cli["productos"]),
                "cortesias_fmt": miles(cli["cortesias"]),
                "monto_fmt": pesos(cli["monto"]),
            }
        )
    salida.sort(key=lambda c: c["monto"], reverse=True)
    return salida


def get_productos_resumen(area, anio=None, mes=None, nombre=None):
    """Tabla de productos del área: cantidad, monto y clientes distintos."""
    filas = _productos_area(area, anio, mes, nombre)
    if not filas:
        return None

    total = sum(int(f["monto"] or 0) for f in filas) or 1
    return [
        {
            "producto": f["producto"],
            "categoria": f["categoria"],
            "cantidad": miles(f["cantidad"]),
            "monto": pesos(f["monto"]),
            "clientes": miles(f["clientes"]),
            "pct": f"{round(int(f['monto'] or 0) * 100.0 / total, 1)}%",
        }
        for f in filas
    ]


def get_ultima_carga(area):
    """Fecha del dato más reciente del área (para la tarjeta de estado)."""
    fuente, params = _fuente_juego(area)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(jornada) AS m FROM ({fuente}) f", params)
            r = cur.fetchone() or {}
            return fecha_hora(r.get("m")) if r.get("m") else None
    finally:
        conn.close()
