"""Módulo Getnet (tabla public.getnet).

Columnas reales: id, id_unico (unique), jornada (date), fecha (timestamp),
monto (integer), slot_attendant, forma_pago, created_at.
"""
from psycopg2.extras import execute_values

from core.database import get_connection
from core.formato import fecha_corta, fecha_hora, mes_anio_es, mes_ingles, miles, pesos

TABLE = "getnet"


def insertar_filas(filas):
    """Inserta filas en la tabla getnet evitando duplicados.

    `filas` es una lista de diccionarios con las claves:
    id_unico, jornada (date), fecha (datetime), monto (int),
    slot_attendant (str), forma_pago (str).

    Para que sea rápido insertamos TODO en un solo viaje a la base de datos
    con execute_values (en vez de un INSERT por fila). Usamos
    ON CONFLICT (id_unico) DO NOTHING: si el id_unico ya existe (registro ya
    cargado antes o duplicado dentro del mismo archivo), simplemente se ignora.

    Con `RETURNING id_unico` la base nos devuelve solo las filas que realmente
    insertó, así contamos cuántas entraron y cuántas se omitieron.

    Devuelve un dict con: inserted (insertadas) y skipped (duplicadas).
    """
    if not filas:
        return {"inserted": 0, "skipped": 0}

    # Convertimos cada dict a una tupla en el ORDEN de las columnas del INSERT.
    valores = [
        (
            f["id_unico"],
            f["jornada"],
            f["fecha"],
            f["monto"],
            f["slot_attendant"],
            f["forma_pago"],
        )
        for f in filas
    ]

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # execute_values arma un único INSERT con muchos VALUES (...).
            # fetch=True nos devuelve las filas del RETURNING (solo las insertadas).
            insertadas = execute_values(
                cur,
                f"""
                INSERT INTO {TABLE}
                    (id_unico, jornada, fecha, monto, slot_attendant, forma_pago)
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
                "hasta_jornada": fecha_corta(max_jornada),
                "total_valor": pesos(r["monto_total"]),
                "total_label": f"{miles(r['cantidad'])} operaciones",
                "ultima_valor": pesos(u.get("m")),
                "ultima_label": f"{miles(u.get('c'))} ops · {fecha_corta(max_jornada)}",
            }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DASHBOARD GETNET — funciones para los gráficos
# ---------------------------------------------------------------------------
#
# Reglas de cálculo (ver FUNCTIONAL_RULES.md y la "Leyenda de cálculos" del
# dashboard):
#
# - La columna `jornada` (date) es la fecha OPERATIVA. La usamos para agrupar
#   por mes y para el día de la semana del mapa de calor.
# - La columna `fecha` (timestamp) trae la hora real de la operación. De ahí
#   sacamos la HORA para los gráficos por hora y el mapa de calor.
# - La Jornada va de 10:00 a 08:00 del día siguiente, por eso las horas se
#   ordenan 10, 11, ... 23, 00, 01, ... 08 (la hora 09 queda fuera de Jornada).
# - "Promedio por hora" = total de esa hora ÷ cantidad de jornadas únicas del
#   periodo filtrado.
# - "Mapa de calor" = total de cada franja (día de semana × hora) ÷ cantidad de
#   jornadas únicas de ese día de la semana.

# Orden de horas dentro de una Jornada (10:00 → 08:00). Se excluye la hora 9.
HORAS_JORNADA = list(range(10, 24)) + list(range(0, 9))

# Nombres de día de la semana. PostgreSQL EXTRACT(DOW): 0=domingo ... 6=sábado.
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
# Mapa DOW de PostgreSQL -> índice 0..6 con Lunes primero.
_DOW_A_INDICE = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}


def _where(anio=None, mes=None, nombre=None):
    """Arma la cláusula WHERE de filtros reutilizable para los gráficos.

    Devuelve (where_sql, params). El filtro de año y mes usa `jornada`; el de
    nombre busca en `slot_attendant`. Si no hay filtros, where_sql es "".
    """
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
    return where, params


def get_operaciones_por_mes(anio=None, mes=None, nombre=None):
    """Cantidad de operaciones agrupadas por mes de la jornada.

    Devuelve un dict {labels: ["Abril 2025", ...], valores: [123, ...]} listo
    para Chart.js, o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       COUNT(*)                      AS cantidad
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
        "valores": [int(f["cantidad"]) for f in filas],
    }


def get_montos_por_mes(anio=None, mes=None, nombre=None):
    """Suma de montos agrupada por mes de la jornada.

    Devuelve {labels: [...], valores: [monto, ...]} o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       SUM(monto)                    AS total
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


def get_promedio_por_hora(anio=None, mes=None, nombre=None):
    """Promedio de operaciones y monto por hora del periodo.

    Para cada hora suma operaciones y monto, y los divide entre la cantidad de
    jornadas únicas del periodo filtrado (así "por hora" es comparable entre
    periodos de distinto tamaño).

    Devuelve {labels: ["10", "11", ...], operaciones: [...], montos: [...]}
    en el orden de Jornada (10 → 08), o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Cantidad de jornadas únicas en el periodo (divisor del promedio).
            cur.execute(
                f"SELECT COUNT(DISTINCT jornada) AS n FROM {TABLE} {where}",
                params,
            )
            total_jornadas = (cur.fetchone() or {}).get("n") or 0
            if not total_jornadas:
                return None

            # Totales por hora (la hora sale de `fecha`, no de la jornada).
            cur.execute(
                f"""
                SELECT EXTRACT(HOUR FROM fecha)::int AS hora,
                       COUNT(*)                        AS ops,
                       SUM(monto)                      AS monto
                FROM {TABLE}
                {where}
                GROUP BY 1
                """,
                params,
            )
            por_hora = {f["hora"]: f for f in cur.fetchall()}
    finally:
        conn.close()

    labels, operaciones, montos = [], [], []
    for h in HORAS_JORNADA:
        fila = por_hora.get(h)
        ops = int(fila["ops"]) if fila else 0
        monto = int(fila["monto"] or 0) if fila else 0
        labels.append(f"{h:02d}")
        operaciones.append(round(ops / total_jornadas, 1))
        montos.append(round(monto / total_jornadas))
    return {"labels": labels, "operaciones": operaciones, "montos": montos}


def get_heatmap_dia_hora(anio=None, mes=None, nombre=None):
    """Mapa de calor: promedio de operaciones por jornada en cada franja día×hora.

    Cada celda = total de operaciones de ese (día de semana × hora) ÷ cantidad
    de jornadas únicas de ese día de la semana en el periodo.

    Devuelve un dict con:
      - horas: ["10", "11", ...] en orden de Jornada
      - dias: ["Lunes", ..., "Domingo"]
      - matriz: lista de 7 filas; cada fila lista de promedios por hora
      - jornadas_por_dia: {"Lunes": 56, ...}
      - total_jornadas, rango_inicio, rango_fin
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Conteo de jornadas únicas por día de la semana + rango de fechas.
            cur.execute(
                f"""
                SELECT EXTRACT(DOW FROM jornada)::int AS dow,
                       COUNT(DISTINCT jornada)         AS jornadas
                FROM {TABLE}
                {where}
                GROUP BY 1
                """,
                params,
            )
            jornadas_dow = {f["dow"]: int(f["jornadas"]) for f in cur.fetchall()}
            if not jornadas_dow:
                return None

            cur.execute(
                f"SELECT MIN(jornada) AS ini, MAX(jornada) AS fin FROM {TABLE} {where}",
                params,
            )
            rango = cur.fetchone() or {}

            # Total de operaciones por (día de semana, hora).
            cur.execute(
                f"""
                SELECT EXTRACT(DOW FROM jornada)::int AS dow,
                       EXTRACT(HOUR FROM fecha)::int   AS hora,
                       COUNT(*)                         AS ops
                FROM {TABLE}
                {where}
                GROUP BY 1, 2
                """,
                params,
            )
            celdas = cur.fetchall()
    finally:
        conn.close()

    # Acumulamos en una matriz [indice_dia][hora] -> total de operaciones.
    totales = {i: {h: 0 for h in HORAS_JORNADA} for i in range(7)}
    for c in celdas:
        idx = _DOW_A_INDICE.get(c["dow"])
        if idx is None or c["hora"] not in totales[idx]:
            continue
        totales[idx][c["hora"]] = int(c["ops"])

    matriz = []
    for i in range(7):
        dow_pg = next(k for k, v in _DOW_A_INDICE.items() if v == i)
        n = jornadas_dow.get(dow_pg, 0)
        fila = []
        for h in HORAS_JORNADA:
            promedio = round(totales[i][h] / n, 1) if n else 0.0
            fila.append(promedio)
        matriz.append(fila)

    jornadas_por_dia = {
        DIAS_SEMANA[i]: jornadas_dow.get(
            next(k for k, v in _DOW_A_INDICE.items() if v == i), 0
        )
        for i in range(7)
    }
    total_jornadas = sum(jornadas_dow.values())

    return {
        "horas": [f"{h:02d}" for h in HORAS_JORNADA],
        "dias": DIAS_SEMANA,
        "matriz": matriz,
        "jornadas_por_dia": jornadas_por_dia,
        "total_jornadas": total_jornadas,
        "rango_inicio": fecha_corta(rango.get("ini")),
        "rango_fin": fecha_corta(rango.get("fin")),
    }
