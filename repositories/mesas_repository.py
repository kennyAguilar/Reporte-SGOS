"""Repositorio del módulo Mesas (tabla public.mesas), usado por Coin In MDJ.

Guarda el detalle por SESIÓN del reporte de juego en mesas ("Traking SGOS").
A diferencia de Coin In MDA (agregado por jugador y día), este reporte NO
viene agregado: puede haber varias filas por cliente el mismo día (una por
cada sesión en una mesa/juego). Por eso las consultas agregan con GROUP BY en
vez de sumar columnas ya agregadas por el reporte de origen.

PUNTOS_OBTENIDOS se guarda tal cual (columna `puntos_obtenidos`) y además se
guarda `coin_in` = PUNTOS_OBTENIDOS * 1000: el "seudo Coin In" que el negocio
usa para comparar el juego de mesas con el Coin In de MDA.

Columnas de la tabla `mesas`:
    id (serial PK), id_unico (text UNIQUE), id_sesion (text),
    id_cliente (text), nombre (text), categoria (text), mesa (text),
    juego (text), fecha_operacion (date), puntos_obtenidos (integer),
    coin_in (bigint), created_at (timestamp).

Este repositorio expone las MISMAS funciones (nombres y forma del
resultado) que repositories/coinin_repository.py, para que modules/coinin.py
lo use en el sistema "MDJ" sin duplicar las vistas/plantillas de Coin In.
El parámetro `sistema` se recibe por compatibilidad de firma pero se ignora
(la tabla `mesas` no distingue sistema).
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_anio_es, mes_ingles, miles, pesos

from psycopg2.extras import execute_values

TABLE = "mesas"

# Colores del donut de categorías (consistentes con Coin In).
_COLORES_NIVEL = [
    "#d4af37", "#24a148", "#78a9ff", "#ff832b",
    "#be95ff", "#08bdba", "#fa4d56", "#a56eff",
]


def ensure_mesas_schema():
    """Crea la tabla `mesas` y sus índices si no existen (idempotente)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id               SERIAL PRIMARY KEY,
                    id_unico         TEXT UNIQUE NOT NULL,
                    id_sesion        TEXT,
                    id_cliente       TEXT,
                    nombre           TEXT,
                    categoria        TEXT,
                    mesa             TEXT,
                    juego            TEXT,
                    fecha_operacion  DATE NOT NULL,
                    puntos_obtenidos INTEGER,
                    coin_in          BIGINT,
                    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_mesas_fecha "
                f"ON {TABLE} (fecha_operacion)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_mesas_cliente "
                f"ON {TABLE} (id_cliente)"
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
            f["id_sesion"],
            f["id_cliente"],
            f["nombre"],
            f["categoria"],
            f["mesa"],
            f["juego"],
            f["fecha_operacion"],
            f["puntos_obtenidos"],
            f["coin_in"],
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
                    (id_unico, id_sesion, id_cliente, nombre, categoria, mesa,
                     juego, fecha_operacion, puntos_obtenidos, coin_in)
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


def _where(anio=None, mes=None, nombre=None, nivel=None):
    """Arma la cláusula WHERE común (equivalente a coinin_repository._where)."""
    filtros, params = ["1 = 1"], []
    if anio:
        filtros.append("EXTRACT(YEAR FROM fecha_operacion) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM fecha_operacion) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(nombre ILIKE %s OR id_cliente ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")
    if nivel:
        filtros.append("categoria = %s")
        params.append(nivel)
    return "WHERE " + " AND ".join(filtros), params


def get_niveles_disponibles(sistema=None):
    """Lista de Categoría distintas, para poblar el filtro."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT categoria
                FROM {TABLE}
                WHERE categoria IS NOT NULL AND categoria <> ''
                ORDER BY 1
                """
            )
            return [f["categoria"] for f in cur.fetchall()]
    finally:
        conn.close()


def get_resumen(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Tarjetas de resumen del header (mes cargado, total, última jornada)."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(fecha_operacion) AS max_jornada,
                       SUM(coin_in)         AS coin_in_total,
                       COUNT(*)             AS filas,
                       MAX(created_at)      AS fecha_carga
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
                f"SELECT SUM(coin_in) AS m, COUNT(DISTINCT id_cliente) AS j "
                f"FROM {TABLE} {where} AND fecha_operacion = %s",
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


def get_kpis_dashboard(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Cuatro KPIs principales del dashboard de Mesas.

    A diferencia de Coin In, "filas" no es jugador-día: es SESIÓN (puede
    haber varias por jugador-día). Por eso se calcula además
    `jugador_dias` (COUNT DISTINCT id_cliente+fecha) para que "Coin In x
    jugador-día" y "Sesiones x jugador-día" sigan siendo comparables a MDA/MDJ.
    """
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)                                    AS sesiones,
                       COUNT(DISTINCT (id_cliente, fecha_operacion)) AS jugador_dias,
                       COUNT(DISTINCT fecha_operacion)              AS dias,
                       COUNT(DISTINCT id_cliente)                   AS jugadores,
                       SUM(coin_in)                                 AS coin_in
                FROM {TABLE}
                {where}
                """,
                params,
            )
            base = cur.fetchone() or {}
    finally:
        conn.close()

    sesiones = int(base.get("sesiones") or 0)
    jugador_dias = int(base.get("jugador_dias") or 0)
    dias = int(base.get("dias") or 0)
    if not sesiones or not dias:
        return None

    coin_in = int(base.get("coin_in") or 0)
    jugadores = int(base.get("jugadores") or 0)

    return {
        "coin_in": pesos(coin_in),
        "coin_in_dia": pesos(round(coin_in / dias)),
        "ticket": pesos(round(coin_in / jugador_dias)) if jugador_dias else pesos(0),
        "dias": miles(dias),
        "jugadores": miles(jugadores),
        "jugadores_dia": miles(round(jugador_dias / dias)) if dias else miles(0),
        "juegos": miles(sesiones),
        "juegos_jugador": (
            miles(round(sesiones / jugador_dias)) if jugador_dias else miles(0)
        ),
        "prom_jugado": pesos(0),
        "pct_promo": "0%",
    }


def get_coin_in_por_mes(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Coin In (equivalente) agrupado por mes de la fecha de operación."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', fecha_operacion) AS mes,
                       SUM(coin_in)                         AS total
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


def get_jugadores_por_mes(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Jugadores únicos por mes de la fecha de operación."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', fecha_operacion) AS mes,
                       COUNT(DISTINCT id_cliente)           AS jugadores
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


def get_niveles(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Distribución de Coin In por Categoría (donut del dashboard)."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(categoria, ''), 'Sin categoría') AS nivel,
                       SUM(coin_in)              AS coin_in,
                       COUNT(DISTINCT id_cliente) AS jugadores
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


def get_top_jugadores(sistema=None, anio=None, mes=None, nombre=None, nivel=None, limit=10):
    """Top de jugadores por Coin In (equivalente) acumulado en el periodo."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id_cliente,
                       MAX(nombre)                          AS full_name,
                       MAX(categoria)                        AS player_level,
                       COUNT(DISTINCT fecha_operacion)       AS dias,
                       SUM(coin_in)                          AS coin_in,
                       COUNT(*)                              AS juegos
                FROM {TABLE}
                {where}
                GROUP BY id_cliente
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
            "player_id": f["id_cliente"],
            "full_name": f["full_name"] or "",
            "player_level": f["player_level"] or "",
            "dias": miles(f["dias"]),
            "coin_in_fmt": pesos(f["coin_in"]),
            "juegos_fmt": miles(f["juegos"]),
        }
        for f in filas
    ]


def get_resumen_mensual(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Tabla del histórico: una fila por mes con los totales del periodo."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', fecha_operacion) AS mes,
                       COUNT(DISTINCT fecha_operacion)      AS dias,
                       COUNT(DISTINCT id_cliente)           AS jugadores,
                       SUM(coin_in)                         AS coin_in,
                       COUNT(*)                             AS juegos
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
                "prom_jugado": pesos(0),
                "juegos": miles(f["juegos"]),
                "coin_in_jugador": pesos(round(coin_in / jugadores)) if jugadores else pesos(0),
            }
        )
    return resultado


def get_detalle_niveles(sistema=None, anio=None, mes=None, nombre=None, nivel=None):
    """Tabla del histórico: totales por Categoría."""
    where, params = _where(anio, mes, nombre, nivel)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(categoria, ''), 'Sin categoría') AS nivel,
                       COUNT(DISTINCT id_cliente) AS jugadores,
                       SUM(coin_in)               AS coin_in,
                       COUNT(*)                   AS juegos
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
                "prom_jugado": pesos(0),
                "juegos": miles(f["juegos"]),
                "coin_in_jugador": pesos(round(coin_in / jugadores)) if jugadores else pesos(0),
            }
        )
    return resultado
