"""Resumen del módulo Getnet (tabla public.getnet_transacciones).

Columnas reales: jornada (date), fecha, id_cliente, monto (numeric),
voucher, slot_attendant, validador, forma_pago, ingreso_cawa,
operacion_uid, archivo_origen, created_at.
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_ingles, miles, pesos

TABLE = "getnet_transacciones"


def get_resumen(anio=None, mes=None, nombre=None):
    """KPIs del módulo Getnet o None si no hay datos en el filtro."""
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

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT MAX(jornada)    AS max_jornada,
                       SUM(monto)      AS monto_total,
                       COUNT(*)        AS cantidad,
                       MAX(created_at) AS fecha_carga
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
                f"SELECT SUM(monto) AS m, COUNT(*) AS c FROM {TABLE} {ujoin}",
                params + [max_jornada],
            )
            u = cur.fetchone() or {}

            return {
                "mes_cargado": mes_ingles(max_jornada),
                "fecha_carga": fecha_hora(r["fecha_carga"]),
                "hasta_jornada": fecha_larga(max_jornada),
                "total_valor": pesos(r["monto_total"]),
                "total_label": f"{miles(r['cantidad'])} operaciones",
                "ultima_valor": pesos(u.get("m")),
                "ultima_label": f"{miles(u.get('c'))} ops · {fecha_larga(max_jornada)}",
            }
    finally:
        conn.close()
