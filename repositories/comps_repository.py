"""Repositorio del módulo COMPS (tabla public.comps).

Columnas reales de la tabla `comps`:
    id (serial PK), id_unico (text UNIQUE), fecha_real (timestamp),
    fecha_jornada (date), cliente_id (text), nombre_cliente (text),
    descripcion_cat (text), descripcion_prod (text), micros (integer),
    estado (text), usuario_id (text), nombre (text), created_at (timestamp).

Solo se guardan las filas cuyo Estado es "QUEMADO" (el filtro se aplica
durante la carga, no en la base). El valor del módulo es la suma de micros.
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_ingles, miles

from psycopg2.extras import execute_values

TABLE = "comps"


def ensure_comps_schema():
    """Crea la tabla `comps` (y su índice) si todavía no existen.

    Es idempotente: CREATE TABLE IF NOT EXISTS permite ejecutarla las veces
    que haga falta sin borrar ni modificar datos ya cargados.

    - id_unico es UNIQUE para evitar duplicados al cargar el Excel
      (se usa con ON CONFLICT (id_unico) DO NOTHING).
    - fecha_real es TIMESTAMP (conserva la hora real del consumo).
    - fecha_jornada es DATE (se recalcula con la regla 10:00 AM a 09:00 AM).
    - El índice por fecha_jornada acelera los filtros por año/mes.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id              SERIAL PRIMARY KEY,
                    id_unico        TEXT UNIQUE NOT NULL,
                    fecha_real      TIMESTAMP NOT NULL,
                    fecha_jornada   DATE NOT NULL,
                    cliente_id      TEXT,
                    nombre_cliente  TEXT,
                    descripcion_cat TEXT,
                    descripcion_prod TEXT,
                    micros          INTEGER,
                    estado          TEXT,
                    usuario_id      TEXT,
                    nombre          TEXT,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_comps_jornada "
                f"ON {TABLE} (fecha_jornada)"
            )
        conn.commit()
    finally:
        conn.close()


def insertar_filas(filas):
    """Inserta filas en la tabla comps evitando duplicados.

    `filas` es una lista de diccionarios con las claves:
    id_unico, fecha_real (datetime), fecha_jornada (date), cliente_id,
    nombre_cliente, descripcion_cat, descripcion_prod, micros (int),
    estado, usuario_id, nombre.

    Igual que en Premios, insertamos TODO en un solo viaje con execute_values.
    Usamos ON CONFLICT (id_unico) DO NOTHING: si el id_unico ya existe
    (registro ya cargado o duplicado dentro del mismo archivo) se ignora.

    Con RETURNING id_unico la base devuelve solo las filas realmente
    insertadas, así contamos cuántas entraron y cuántas se omitieron.

    Devuelve un dict con: inserted (insertadas) y skipped (duplicadas).
    """
    if not filas:
        return {"inserted": 0, "skipped": 0}

    # Convertimos cada dict a una tupla en el ORDEN de las columnas del INSERT.
    valores = [
        (
            f["id_unico"],
            f["fecha_real"],
            f["fecha_jornada"],
            f["cliente_id"],
            f["nombre_cliente"],
            f["descripcion_cat"],
            f["descripcion_prod"],
            f["micros"],
            f["estado"],
            f["usuario_id"],
            f["nombre"],
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
                    (id_unico, fecha_real, fecha_jornada, cliente_id,
                     nombre_cliente, descripcion_cat, descripcion_prod,
                     micros, estado, usuario_id, nombre)
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

    skipped = len(filas) - inserted
    return {"inserted": inserted, "skipped": skipped}


def get_resumen(anio=None, mes=None, nombre=None):
    """KPIs del módulo COMPS o None si no hay datos en el filtro."""
    filtros, params = [], []
    if anio:
        filtros.append("EXTRACT(YEAR FROM fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(nombre_cliente ILIKE %s OR nombre ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(fecha_jornada) AS max_jornada,
                       SUM(micros)        AS micros_total,
                       COUNT(*)           AS cantidad,
                       MAX(created_at)    AS fecha_carga
                FROM {TABLE}
                {where}
                """,
                params,
            )
            r = cur.fetchone()
            if not r or not r["cantidad"]:
                return None

            max_jornada = r["max_jornada"]
            ujoin = (where + " AND " if where else "WHERE ") + "fecha_jornada = %s"
            cur.execute(
                f"SELECT SUM(micros) AS m, COUNT(*) AS c FROM {TABLE} {ujoin}",
                params + [max_jornada],
            )
            u = cur.fetchone() or {}

            return {
                "mes_cargado": mes_ingles(max_jornada),
                "fecha_carga": fecha_hora(r["fecha_carga"]),
                "hasta_jornada": fecha_larga(max_jornada),
                "total_label_titulo": "Micros totales del mes",
                "total_valor": miles(r["micros_total"]),
                "total_label": f"{miles(r['cantidad'])} comps",
                "ultima_valor": miles(u.get("m")),
                "ultima_label": f"{miles(u.get('c'))} comps · {fecha_larga(max_jornada)}",
            }
    finally:
        conn.close()
