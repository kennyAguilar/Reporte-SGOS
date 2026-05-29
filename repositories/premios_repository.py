"""Resumen del módulo Premios (tabla public.premios_transacciones).

Columnas reales: fecha, jornada (date), cliente, transferencia_final (numeric),
slot_attendant, tipo_pago, operacion_uid, archivo_origen, created_at.
El monto del módulo es la Transferencia Final.
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_ingles, miles, pesos

TABLE = "premios_transacciones"


def get_resumen(anio=None, mes=None, nombre=None):
    """KPIs del módulo Premios o None si no hay datos en el filtro."""
    filtros, params = [], []
    if anio:
        filtros.append("EXTRACT(YEAR FROM jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(slot_attendant ILIKE %s OR cliente ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(jornada)             AS max_jornada,
                       SUM(transferencia_final) AS monto_total,
                       COUNT(*)                 AS cantidad,
                       MAX(created_at)          AS fecha_carga
                FROM {TABLE}
                {where}
                """,
                params,
            )
            r = cur.fetchone()
            if not r or not r["cantidad"]:
                return None

            max_jornada = r["max_jornada"]
            ujoin = (where + " AND " if where else "WHERE ") + "jornada = %s"
            cur.execute(
                f"SELECT SUM(transferencia_final) AS m, COUNT(*) AS c FROM {TABLE} {ujoin}",
                params + [max_jornada],
            )
            u = cur.fetchone() or {}

            return {
                "mes_cargado": mes_ingles(max_jornada),
                "fecha_carga": fecha_hora(r["fecha_carga"]),
                "hasta_jornada": fecha_larga(max_jornada),
                "total_valor": pesos(r["monto_total"]),
                "total_label": f"{miles(r['cantidad'])} premios",
                "ultima_valor": pesos(u.get("m")),
                "ultima_label": f"{miles(u.get('c'))} premios · {fecha_larga(max_jornada)}",
            }
    finally:
        conn.close()
