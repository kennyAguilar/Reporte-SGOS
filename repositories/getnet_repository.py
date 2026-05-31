"""Módulo Getnet (tabla public.getnet).

Columnas reales: id, id_unico (unique), jornada (date), fecha (timestamp),
monto (integer), slot_attendant, forma_pago, created_at.
"""
from datetime import datetime

from psycopg2.extras import execute_values

from core.database import get_connection
from core.formato import fecha_corta, fecha_hora, mes_anio_es, mes_ingles, miles, pesos

TABLE = "getnet"

# Excluye de TODAS las estadísticas de Getnet a los slot attendants marcados
# como inactivos en el apartado de Configuración. Los que no están en la tabla
# `slot_attendants` se consideran activos por defecto. Se usa NOT EXISTS para
# que la consulta no falle aunque la tabla aún no exista (LEFT semantics).
_FILTRO_ACTIVOS = (
    "slot_attendant NOT IN "
    "(SELECT nombre FROM slot_attendants WHERE activo = false)"
)


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
    filtros.append(_FILTRO_ACTIVOS)

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
    filtros.append(_FILTRO_ACTIVOS)
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    return where, params


# Colores de las formas de pago para el donut (consistentes con DESIGN.md).
_COLORES_FORMA = ["#d4af37", "#24a148", "#78a9ff", "#ff832b", "#be95ff", "#08bdba"]


def get_kpis_dashboard(anio=None, mes=None, nombre=None):
    """KPIs resumidos para las tarjetas del dashboard.

    Devuelve un dict con:
        - total_ops, dias, promedio_ops
        - monto_total, ticket
        - hora_pico ("HH:00"), ops_pico_prom
        - formas: [{"label", "ops", "monto", "pct", "color"}, ...] para el donut
    o None si no hay datos en el filtro. Los promedios usan la cantidad de
    jornadas únicas (días contados) como divisor.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)                AS total_ops,
                       COUNT(DISTINCT jornada) AS dias,
                       SUM(monto)              AS monto_total
                FROM {TABLE}
                {where}
                """,
                params,
            )
            base = cur.fetchone() or {}
            total_ops = int(base.get("total_ops") or 0)
            dias = int(base.get("dias") or 0)
            if not total_ops or not dias:
                return None
            monto_total = int(base.get("monto_total") or 0)

            # Hora pico: la hora con más operaciones (la hora sale de `fecha`).
            cur.execute(
                f"""
                SELECT EXTRACT(HOUR FROM fecha)::int AS hora,
                       COUNT(*)                        AS ops
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY ops DESC
                LIMIT 1
                """,
                params,
            )
            pico = cur.fetchone() or {}

            # Distribución por forma de pago (para el donut).
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(forma_pago), ''), 'Sin especificar') AS forma,
                       COUNT(*)   AS ops,
                       SUM(monto) AS monto
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY ops DESC
                """,
                params,
            )
            filas_forma = cur.fetchall()
    finally:
        conn.close()

    ops_pico = int(pico.get("ops") or 0)
    hora_pico = pico.get("hora")

    formas = []
    for i, f in enumerate(filas_forma):
        ops = int(f["ops"])
        formas.append(
            {
                "label": f["forma"],
                "ops": ops,
                "monto": int(f["monto"] or 0),
                "pct": round(ops * 100 / total_ops, 1),
                "color": _COLORES_FORMA[i % len(_COLORES_FORMA)],
            }
        )

    return {
        "total_ops": miles(total_ops),
        "dias": miles(dias),
        "promedio_ops": miles(round(total_ops / dias)),
        "monto_total": pesos(monto_total),
        "ticket": pesos(round(monto_total / total_ops)),
        "hora_pico": f"{hora_pico:02d}:00" if hora_pico is not None else "—",
        "ops_pico_prom": miles(round(ops_pico / dias)),
        "formas": formas,
    }


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


def get_resumen_mensual(anio=None, mes=None, nombre=None):
    """Resumen del Histórico por mes: operaciones, monto y ticket promedio.

    Agrupa por mes de la `jornada`. Devuelve un dict:
        {
          "filas": [{"mes": "Enero 2026", "ops": N, "monto": M, "ticket": T}, ...],
          "total_ops": ..., "total_monto": ..., "ticket": ...
        }
    o None si no hay datos. Las filas van de más reciente a más antiguo.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       COUNT(*)                      AS ops,
                       SUM(monto)                    AS monto
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY 1 DESC
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    out = []
    total_ops = total_monto = 0
    for f in filas:
        ops = int(f["ops"])
        monto = int(f["monto"] or 0)
        total_ops += ops
        total_monto += monto
        out.append(
            {
                "mes": mes_anio_es(f["mes"]),
                "ops": miles(ops),
                "monto": pesos(monto),
                "ticket": pesos(round(monto / ops)) if ops else pesos(0),
            }
        )
    return {
        "filas": out,
        "total_ops": miles(total_ops),
        "total_monto": pesos(total_monto),
        "ticket": pesos(round(total_monto / total_ops)) if total_ops else pesos(0),
    }


def get_operaciones_por_hora(anio=None, mes=None, nombre=None):
    """Detalle del Histórico por hora: totales y promedios por jornada.

    Para cada hora (orden de Jornada 10→08) entrega el total de operaciones y
    monto del periodo, y su promedio por jornada (÷ jornadas únicas). Devuelve:
        {
          "filas": [{"hora": "10:00", "ops": .., "monto": .., "ops_prom": ..,
                     "monto_prom": .., "es_pico": bool}, ...],
          "jornadas": J, "total_ops": .., "total_monto": ..,
          "ops_prom": .., "monto_prom": ..
        }
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(DISTINCT jornada) AS n FROM {TABLE} {where}",
                params,
            )
            jornadas = (cur.fetchone() or {}).get("n") or 0
            if not jornadas:
                return None

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

    # Hora pico = la de mayor número de operaciones (para resaltarla).
    hora_pico = None
    max_ops = -1
    for h, f in por_hora.items():
        if int(f["ops"]) > max_ops:
            max_ops = int(f["ops"])
            hora_pico = h

    filas = []
    total_ops = total_monto = 0
    for h in HORAS_JORNADA:
        f = por_hora.get(h)
        ops = int(f["ops"]) if f else 0
        monto = int(f["monto"] or 0) if f else 0
        total_ops += ops
        total_monto += monto
        filas.append(
            {
                "hora": f"{h:02d}:00",
                "ops": miles(ops),
                "monto": pesos(monto),
                "ops_prom": round(ops / jornadas, 1),
                "monto_prom": pesos(round(monto / jornadas)),
                "es_pico": h == hora_pico and ops > 0,
            }
        )
    return {
        "filas": filas,
        "jornadas": miles(jornadas),
        "total_ops": miles(total_ops),
        "total_monto": pesos(total_monto),
        "ops_prom": round(total_ops / jornadas, 1),
        "monto_prom": pesos(round(total_monto / jornadas)),
    }


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


# ---------------------------------------------------------------------------
# RECORD ASISTENTES — métricas por slot attendant
# ---------------------------------------------------------------------------
#
# Todas estas funciones reutilizan _where() (que aplica los filtros de año, mes
# y nombre, y excluye a los slot attendants marcados como inactivos en
# Configuración). Así el filtro del header influye en toda la sección.


def get_record_jornadas(anio=None, mes=None, nombre=None):
    """Record de transacciones en UNA jornada por cada asistente.

    Para cada slot attendant busca la jornada donde hizo más transacciones (su
    mejor día) y devuelve esos records ordenados de mayor a menor.

    Devuelve una lista de dicts {nombre, ops, fecha} o [] si no hay datos. El
    `fecha` ya viene formateado como dd/mm/aaaa.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre, jornada, COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant, jornada
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return []

    # Por cada asistente nos quedamos con su jornada de más operaciones.
    mejor = {}
    for f in filas:
        nom = f["nombre"]
        actual = mejor.get(nom)
        if actual is None or f["ops"] > actual["ops"]:
            mejor[nom] = {"ops": int(f["ops"]), "jornada": f["jornada"]}

    records = [
        {"nombre": nom, "ops": v["ops"], "fecha": fecha_corta(v["jornada"])}
        for nom, v in mejor.items()
    ]
    records.sort(key=lambda r: r["ops"], reverse=True)
    return records


def get_resumen_asistentes(anio=None, mes=None, nombre=None):
    """Resumen de métricas por asistente, ordenado por total de transacciones.

    Para cada slot attendant calcula:
      - total      : cantidad de transacciones
      - ticket      : ticket promedio = SUM(monto) / COUNT(*) (monto por operación)
      - franja      : hora del día con más transacciones ("HH:00")
      - mejor_ops   : nº de transacciones de su mejor jornada
      - mejor_fecha : fecha de esa mejor jornada (dd/mm/aaaa)

    Devuelve una lista de dicts o [].
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Totales y ticket promedio por asistente.
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre,
                       COUNT(*)        AS total,
                       SUM(monto)      AS monto
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant
                """,
                params,
            )
            base = {f["nombre"]: dict(f) for f in cur.fetchall()}
            if not base:
                return []

            # Hora con más transacciones por asistente.
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre,
                       EXTRACT(HOUR FROM fecha)::int AS hora,
                       COUNT(*)                       AS ops
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant, hora
                """,
                params,
            )
            franja = {}
            for f in cur.fetchall():
                nom = f["nombre"]
                actual = franja.get(nom)
                if actual is None or f["ops"] > actual["ops"]:
                    franja[nom] = {"hora": f["hora"], "ops": int(f["ops"])}

            # Mejor jornada por asistente (nº de ops y fecha).
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre, jornada, COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant, jornada
                """,
                params,
            )
            mejor = {}
            for f in cur.fetchall():
                nom = f["nombre"]
                actual = mejor.get(nom)
                if actual is None or f["ops"] > actual["ops"]:
                    mejor[nom] = {"ops": int(f["ops"]), "jornada": f["jornada"]}
    finally:
        conn.close()

    resultado = []
    for nom, b in base.items():
        total = int(b["total"])
        monto = int(b["monto"] or 0)
        ticket = round(monto / total) if total else 0
        fr = franja.get(nom)
        mj = mejor.get(nom)
        resultado.append(
            {
                "nombre": nom,
                "total": total,
                "ticket": pesos(ticket),
                "franja": f"{fr['hora']:02d}:00" if fr else "—",
                "mejor_ops": mj["ops"] if mj else 0,
                "mejor_fecha": fecha_corta(mj["jornada"]) if mj else "—",
            }
        )
    resultado.sort(key=lambda r: r["total"], reverse=True)
    return resultado


def get_transacciones_mes_anio(anio=None, mes=None, nombre=None):
    """Transacciones por mes de cada asistente, separadas por año.

    Devuelve una lista de años (de mayor a menor), cada uno con su tabla:
        [
          {
            "anio": 2026,
            "meses": ["Ene", ..., "Dic"],
            "filas": [{"nombre": ..., "valores": [12 ints], "total": N}, ...],
            "totales": [12 ints],   # total por mes (pie de tabla)
            "total": N              # total del año
          }, ...
        ]
    o [] si no hay datos. Las filas se ordenan por total del año desc.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT EXTRACT(YEAR FROM jornada)::int  AS anio,
                       EXTRACT(MONTH FROM jornada)::int AS mes,
                       slot_attendant                    AS nombre,
                       COUNT(*)                          AS ops
                FROM {TABLE}
                {where}
                GROUP BY anio, mes, nombre
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return []

    meses_abbr = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

    # estructura: anios[anio][nombre] = [12 ints]
    anios = {}
    for f in filas:
        a = anios.setdefault(f["anio"], {})
        fila = a.setdefault(f["nombre"], [0] * 12)
        fila[f["mes"] - 1] = int(f["ops"])

    resultado = []
    for a in sorted(anios.keys(), reverse=True):
        asistentes = anios[a]
        filas_out = [
            {"nombre": nom, "valores": vals, "total": sum(vals)}
            for nom, vals in asistentes.items()
        ]
        filas_out.sort(key=lambda r: r["total"], reverse=True)
        totales = [sum(asistentes[nom][i] for nom in asistentes) for i in range(12)]
        resultado.append(
            {
                "anio": a,
                "meses": meses_abbr,
                "filas": filas_out,
                "totales": totales,
                "total": sum(totales),
            }
        )
    return resultado


def get_total_por_anio(anio=None, mes=None, nombre=None):
    """Total acumulado de transacciones por asistente y año.

    Las columnas son SIEMPRE los últimos 5 años (año actual y los 4 anteriores),
    aunque algunos todavía no tengan datos (se muestran en 0). Así la tabla deja
    espacio para comparar la evolución a medida que se cargan más años.

    Devuelve un dict:
        {
          "anios": [2022, 2023, 2024, 2025, 2026],
          "filas": [{"nombre": ..., "valores": [...], "total": N}, ...],
          "totales": [...],
          "total": N
        }
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT EXTRACT(YEAR FROM jornada)::int AS anio,
                       slot_attendant                   AS nombre,
                       COUNT(*)                         AS ops
                FROM {TABLE}
                {where}
                GROUP BY anio, nombre
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    # Columnas fijas: últimos 5 años (incluye años sin datos, en 0).
    anio_actual = datetime.now().year
    anios = list(range(anio_actual - 4, anio_actual + 1))
    idx = {a: i for i, a in enumerate(anios)}

    por_nombre = {}
    for f in filas:
        # Ignora datos fuera de la ventana de 5 años (por si hubiera años viejos).
        if f["anio"] not in idx:
            continue
        vals = por_nombre.setdefault(f["nombre"], [0] * len(anios))
        vals[idx[f["anio"]]] = int(f["ops"])

    if not por_nombre:
        return None

    filas_out = [
        {"nombre": nom, "valores": vals, "total": sum(vals)}
        for nom, vals in por_nombre.items()
    ]
    filas_out.sort(key=lambda r: r["total"], reverse=True)
    totales = [sum(por_nombre[nom][i] for nom in por_nombre) for i in range(len(anios))]

    return {
        "anios": anios,
        "filas": filas_out,
        "totales": totales,
        "total": sum(totales),
    }
