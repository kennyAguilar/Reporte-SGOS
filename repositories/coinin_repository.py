"""Repositorio del módulo Coin In (tabla public.coinin).

Guarda el reporte diario por jugador de los sistemas MDA y MDJ. Como los dos
Excel tienen la misma estructura, comparten tabla y se distinguen por la
columna `sistema` ('MDA' / 'MDJ'). Eso permite que Coin In Cero consulte ambos
sin duplicar consultas.

Columnas de la tabla `coinin`:
    id (serial PK), id_unico (text UNIQUE), sistema (text), jornada (date),
    player_id (text), full_name (text), player_level (text),
    coin_in (bigint), prom_jugado (bigint), total_games (integer),
    created_at (timestamp).

El Excel ya viene agregado: una fila por jugador y por Gaming Date.
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_anio_es, mes_ingles, miles, pesos

from psycopg2.extras import execute_values

TABLE = "coinin"

# Colores del donut de niveles (consistentes con DESIGN.md).
_COLORES_NIVEL = [
    "#d4af37", "#24a148", "#78a9ff", "#ff832b",
    "#be95ff", "#08bdba", "#fa4d56", "#a56eff",
]


def ensure_coinin_schema():
    """Crea la tabla `coinin` y sus índices si no existen (idempotente)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id           SERIAL PRIMARY KEY,
                    id_unico     TEXT UNIQUE NOT NULL,
                    sistema      TEXT NOT NULL,
                    jornada      DATE NOT NULL,
                    player_id    TEXT,
                    full_name    TEXT,
                    player_level TEXT,
                    coin_in      BIGINT,
                    prom_jugado  BIGINT,
                    total_games  BIGINT,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_coinin_jornada "
                f"ON {TABLE} (sistema, jornada)"
            )
        conn.commit()
    finally:
        conn.close()


def insertar_filas(filas):
    """Inserta filas evitando duplicados (ON CONFLICT por id_unico).

    Devuelve {'inserted': n, 'skipped': n}.
    """
    if not filas:
        return {"inserted": 0, "skipped": 0}

    valores = [
        (
            f["id_unico"],
            f["sistema"],
            f["jornada"],
            f["player_id"],
            f["full_name"],
            f["player_level"],
            f["coin_in"],
            f["prom_jugado"],
            f["total_games"],
        )
        for f in filas
    ]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            insertadas = execute_values(
                cur,
                f"""
                INSERT INTO {TABLE}
                    (id_unico, sistema, jornada, player_id, full_name,
                     player_level, coin_in, prom_jugado, total_games)
                VALUES %s
                ON CONFLICT (id_unico) DO NOTHING
                RETURNING id_unico
                """,
                valores,
                fetch=True,
            )
            inserted = len(insertadas)
        conn.commit()
    finally:
        conn.close()

    return {"inserted": inserted, "skipped": len(filas) - inserted}


def _where(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Arma la cláusula WHERE común. El sistema (MDA/MDJ) siempre filtra."""
    filtros, params = ["sistema = %s"], [sistema]
    if anio:
        filtros.append("EXTRACT(YEAR FROM jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(full_name ILIKE %s OR player_id ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")
    if nivel:
        filtros.append("player_level = %s")
        params.append(nivel)
    return "WHERE " + " AND ".join(filtros), params


def get_niveles_disponibles(sistema):
    """Lista de Player Level distintos para el sistema, para poblar el filtro."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT player_level
                FROM {TABLE}
                WHERE sistema = %s AND player_level IS NOT NULL AND player_level <> ''
                ORDER BY 1
                """,
                [sistema],
            )
            return [f["player_level"] for f in cur.fetchall()]
    finally:
        conn.close()


def get_resumen(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Tarjetas de resumen del header (mes cargado, total, última jornada)."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(jornada)     AS max_jornada,
                       SUM(coin_in)     AS coin_in_total,
                       COUNT(*)         AS filas,
                       MAX(created_at)  AS fecha_carga
                FROM {TABLE}
                {where}
                """,
                params,
            )
            r = cur.fetchone()
            if not r or not r["filas"]:
                return None

            max_jornada = r["max_jornada"]
            cur.execute(
                f"SELECT SUM(coin_in) AS m, COUNT(DISTINCT player_id) AS j "
                f"FROM {TABLE} {where} AND jornada = %s",
                params + [max_jornada],
            )
            u = cur.fetchone() or {}

            return {
                "mes_cargado": mes_ingles(max_jornada),
                "fecha_carga": fecha_hora(r["fecha_carga"]),
                "hasta_jornada": fecha_larga(max_jornada),
                "total_label_titulo": (
                    "Coin In del mes" if mes else "Coin In acumulado"
                ),
                "total_valor": pesos(r["coin_in_total"]),
                "total_label": f"{miles(r['filas'])} registros",
                "ultima_valor": pesos(u.get("m")),
                "ultima_label": (
                    f"{miles(u.get('j'))} jugadores · {fecha_larga(max_jornada)}"
                ),
            }
    finally:
        conn.close()


def get_kpis_dashboard(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Cuatro KPIs principales del dashboard de Coin In.

    - Coin In total, promedio por jornada y ticket promedio por jugador-día.
    - Jugadores únicos y promedio de jugadores por jornada.
    - Juegos jugados y promedio por jugador-día.
    - Prom Jugado (crédito promocional) y su peso sobre el Coin In.
    """
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)                     AS filas,
                       COUNT(DISTINCT jornada)      AS dias,
                       COUNT(DISTINCT player_id)    AS jugadores,
                       SUM(coin_in)                 AS coin_in,
                       SUM(prom_jugado)             AS prom_jugado,
                       SUM(total_games)             AS juegos
                FROM {TABLE}
                {where}
                """,
                params,
            )
            base = cur.fetchone() or {}
    finally:
        conn.close()

    filas = int(base.get("filas") or 0)
    dias = int(base.get("dias") or 0)
    if not filas or not dias:
        return None

    coin_in = int(base.get("coin_in") or 0)
    prom_jugado = int(base.get("prom_jugado") or 0)
    juegos = int(base.get("juegos") or 0)
    jugadores = int(base.get("jugadores") or 0)
    pct_promo = round(prom_jugado * 100.0 / coin_in, 1) if coin_in else 0.0

    return {
        "coin_in": pesos(coin_in),
        "coin_in_dia": pesos(round(coin_in / dias)),
        "ticket": pesos(round(coin_in / filas)),
        "dias": miles(dias),
        "jugadores": miles(jugadores),
        "jugadores_dia": miles(round(filas / dias)),
        "juegos": miles(juegos),
        "juegos_jugador": miles(round(juegos / filas)),
        "prom_jugado": pesos(prom_jugado),
        "pct_promo": f"{pct_promo}%",
    }


def get_coin_in_por_mes(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Coin In agrupado por mes de la jornada."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       SUM(coin_in)                 AS total
                FROM {TABLE}
                {where}
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
        "valores": [int(f["total"] or 0) for f in filas],
    }


def get_jugadores_por_mes(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Jugadores únicos por mes de la jornada."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada)  AS mes,
                       COUNT(DISTINCT player_id)     AS jugadores
                FROM {TABLE}
                {where}
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
        "valores": [int(f["jugadores"] or 0) for f in filas],
    }


def get_niveles(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Distribución de Coin In por Player Level (donut del dashboard)."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(player_level, ''), 'Sin nivel') AS nivel,
                       SUM(coin_in)              AS coin_in,
                       COUNT(DISTINCT player_id) AS jugadores
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY 2 DESC
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    total = sum(int(f["coin_in"] or 0) for f in filas) or 1
    return [
        {
            "label": f["nivel"],
            "coin_in": int(f["coin_in"] or 0),
            "jugadores": int(f["jugadores"] or 0),
            "pct": round(int(f["coin_in"] or 0) * 100.0 / total, 1),
            "color": _COLORES_NIVEL[i % len(_COLORES_NIVEL)],
        }
        for i, f in enumerate(filas)
    ]


def get_top_jugadores(sistema, anio=None, mes=None, nombre=None, nivel=None, limit=10):
    """Top de jugadores por Coin In acumulado en el periodo filtrado."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT player_id,
                       MAX(full_name)          AS full_name,
                       MAX(player_level)       AS player_level,
                       COUNT(DISTINCT jornada) AS dias,
                       SUM(coin_in)            AS coin_in,
                       SUM(total_games)        AS juegos
                FROM {TABLE}
                {where}
                GROUP BY player_id
                ORDER BY SUM(coin_in) DESC NULLS LAST
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
            "player_id": f["player_id"],
            "full_name": f["full_name"] or "",
            "player_level": f["player_level"] or "",
            "dias": miles(f["dias"]),
            "coin_in_fmt": pesos(f["coin_in"]),
            "juegos_fmt": miles(f["juegos"]),
        }
        for f in filas
    ]


def get_resumen_mensual(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Tabla del histórico: una fila por mes con los totales del periodo."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       COUNT(DISTINCT jornada)      AS dias,
                       COUNT(DISTINCT player_id)    AS jugadores,
                       SUM(coin_in)                 AS coin_in,
                       SUM(prom_jugado)             AS prom_jugado,
                       SUM(total_games)             AS juegos
                FROM {TABLE}
                {where}
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

    resultado = []
    for f in filas:
        jugadores = int(f["jugadores"] or 0)
        coin_in = int(f["coin_in"] or 0)
        resultado.append(
            {
                "mes": mes_anio_es(f["mes"]),
                "dias": miles(f["dias"]),
                "jugadores": miles(jugadores),
                "coin_in": pesos(coin_in),
                "prom_jugado": pesos(f["prom_jugado"]),
                "juegos": miles(f["juegos"]),
                "coin_in_jugador": pesos(round(coin_in / jugadores)) if jugadores else pesos(0),
            }
        )
    return resultado


def get_detalle_niveles(sistema, anio=None, mes=None, nombre=None, nivel=None):
    """Tabla del histórico: totales por Player Level."""
    where, params = _where(sistema, anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(player_level, ''), 'Sin nivel') AS nivel,
                       COUNT(DISTINCT player_id) AS jugadores,
                       SUM(coin_in)              AS coin_in,
                       SUM(prom_jugado)          AS prom_jugado,
                       SUM(total_games)          AS juegos
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY 3 DESC NULLS LAST
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    resultado = []
    for f in filas:
        jugadores = int(f["jugadores"] or 0)
        coin_in = int(f["coin_in"] or 0)
        resultado.append(
            {
                "nivel": f["nivel"],
                "jugadores": miles(jugadores),
                "coin_in": pesos(coin_in),
                "prom_jugado": pesos(f["prom_jugado"]),
                "juegos": miles(f["juegos"]),
                "coin_in_jugador": pesos(round(coin_in / jugadores)) if jugadores else pesos(0),
            }
        )
    return resultado
