"""Registro de cargas (tabla public.upload_log).

Columnas reales: tipo, archivo, usuario, rows_total, rows_inserted,
rows_skipped, uploaded_at.
"""
from core.database import get_connection
from core.formato import fecha_hora

TABLE = "upload_log"


def get_ultimo_archivo(tipo=None):
    """Devuelve el último archivo cargado (nombre y fecha) o None.

    Si se indica `tipo` (getnet/premios/comps), filtra por ese módulo.
    """
    filtros, params = [], []
    if tipo:
        filtros.append("tipo = %s")
        params.append(tipo)

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT archivo, uploaded_at
                FROM {TABLE}
                {where}
                ORDER BY uploaded_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "archivo": row["archivo"],
                "fecha": fecha_hora(row["uploaded_at"]),
            }
    finally:
        conn.close()


def registrar_carga(tipo, archivo, usuario, rows_total, rows_inserted, rows_skipped):
    """Guarda en upload_log un registro de la carga realizada.

    - tipo: módulo de la carga (ej: "getnet").
    - archivo: nombre del archivo subido.
    - usuario: quién hizo la carga.
    - rows_total / rows_inserted / rows_skipped: resumen de la carga.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (tipo, archivo, usuario, rows_total, rows_inserted, rows_skipped)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tipo, archivo, usuario, rows_total, rows_inserted, rows_skipped),
            )
        conn.commit()
    finally:
        conn.close()
