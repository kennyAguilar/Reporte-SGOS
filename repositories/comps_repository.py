"""Resumen del módulo COMPS (tabla public.comps_transacciones).

Columnas reales: comps_uid, consumo_id, fecha_jornada (date), cliente_id,
nombre_cliente, descripcion_cat, descripcion_prod, micros (numeric), estado,
usuario_id, nombre_usuario, archivo_origen, created_at.
El valor del módulo es la suma de micros (sin símbolo de pesos).
"""
from core.database import get_connection
from core.formato import fecha_hora, fecha_larga, mes_ingles, miles

TABLE = "comps_transacciones"


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
        filtros.append("(nombre_cliente ILIKE %s OR nombre_usuario ILIKE %s)")
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
