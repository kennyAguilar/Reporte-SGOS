"""Repositorio del módulo Premios (tabla public.premios).

Columnas reales de la tabla `premios`:
    id (serial PK), id_unico (text UNIQUE), fecha (timestamp), jornada (date),
    maquina (text), cliente (text), transferencia_final (integer),
    slot_attendant (text), tipo_de_pago (text), created_at (timestamp).

El "monto" del módulo Premios es la columna transferencia_final.

La tabla guarda TODOS los tipos de pago. El filtro a los tipos de premio
(Jackpot HP / Progressive Jackpot HP) se aplica SOLO en los gráficos de monto
que lo requieren (montos por mes y montos por hora), no globalmente.
"""
from datetime import datetime

from core.database import get_connection
from core.formato import (
    fecha_corta,
    fecha_hora,
    fecha_larga,
    mes_anio_es,
    mes_ingles,
    miles,
    pesos,
)

from psycopg2.extras import execute_values

TABLE = "premios"

# Tipos de pago que se consideran "premios" para los gráficos de MONTO.
# El texto debe coincidir exactamente con el del Excel.
TIPOS_PREMIOS = ("Jackpot HP", "Progressive Jackpot HP")
_FILTRO_TIPOS = "tipo_de_pago IN ('Jackpot HP', 'Progressive Jackpot HP')"

# Orden de horas dentro de una Jornada (10:00 -> 08:00). Se excluye la hora 9.
HORAS_JORNADA = list(range(10, 24)) + list(range(0, 9))

# Nombres de día de la semana. PostgreSQL EXTRACT(DOW): 0=domingo ... 6=sábado.
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
# Mapa DOW de PostgreSQL -> índice 0..6 con Lunes primero.
_DOW_A_INDICE = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}


def ensure_premios_schema():
    """Crea la tabla `premios` (y su índice) si todavía no existen.

    Es idempotente: usar CREATE TABLE IF NOT EXISTS permite ejecutarla las
    veces que haga falta sin borrar ni modificar datos ya cargados.

    - id_unico es UNIQUE para poder evitar duplicados al cargar el Excel
      (más adelante se usará con ON CONFLICT (id_unico) DO NOTHING).
    - fecha y jornada se guardan como DATE (la hora solo se usa al calcular
      la jornada durante la carga, no se almacena).
    - El índice por jornada acelera los filtros por año/mes de los dashboards.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id                  SERIAL PRIMARY KEY,
                    id_unico            TEXT UNIQUE NOT NULL,
                    fecha               TIMESTAMP NOT NULL,
                    jornada             DATE NOT NULL,
                    maquina             TEXT,
                    cliente             TEXT,
                    transferencia_final INTEGER NOT NULL,
                    slot_attendant      TEXT,
                    tipo_de_pago        TEXT,
                    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_premios_jornada "
                f"ON {TABLE} (jornada)"
            )
        conn.commit()
    finally:
        conn.close()


def insertar_filas(filas):
    """Inserta filas en la tabla premios evitando duplicados.

    `filas` es una lista de diccionarios con las claves:
    id_unico, fecha (date), jornada (date), maquina (str), cliente (str),
    transferencia_final (int), slot_attendant (str), tipo_de_pago (str).

    Igual que en Getnet, insertamos TODO en un solo viaje con execute_values
    (mucho más rápido que un INSERT por fila). Usamos
    ON CONFLICT (id_unico) DO NOTHING: si el id_unico ya existe (registro ya
    cargado o duplicado dentro del mismo archivo), simplemente se ignora.

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
            f["fecha"],
            f["jornada"],
            f["maquina"],
            f["cliente"],
            f["transferencia_final"],
            f["slot_attendant"],
            f["tipo_de_pago"],
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
                    (id_unico, fecha, jornada, maquina, cliente,
                     transferencia_final, slot_attendant, tipo_de_pago)
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


# ---------------------------------------------------------------------------
# DASHBOARD — gráficos por mes, por hora y mapa de calor
# ---------------------------------------------------------------------------
#
# REGLA DE FILTRADO POR TIPO DE PAGO:
#   La tabla guarda TODOS los tipos de pago. Los gráficos de OPERACIONES y el
#   mapa de calor usan TODOS los tipos. Los gráficos de MONTO (montos por mes y
#   montos por hora) usan SOLO los tipos premio (_FILTRO_TIPOS).


def _where(anio=None, mes=None, nombre=None):
    """Arma la cláusula WHERE común de los gráficos (sin filtro de tipo de pago).

    El año y el mes filtran por `jornada`; el nombre busca en `slot_attendant`
    o `cliente`. Devuelve (where_sql, params). Si no hay filtros, where_sql es "".
    """
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
    return where, params


def _and_tipos(where):
    """Añade el filtro de tipos premio a una cláusula WHERE existente."""
    if where:
        return where + " AND " + _FILTRO_TIPOS
    return "WHERE " + _FILTRO_TIPOS


def get_kpis_dashboard(anio=None, mes=None, nombre=None):
    """KPIs de las tarjetas del dashboard de Premios.

    Operaciones y días usan TODOS los tipos de pago; el monto total y el ticket
    usan SOLO los tipos premio. Devuelve un dict o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    where_tipos = _and_tipos(where)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Operaciones y días (todos los tipos).
            cur.execute(
                f"""
                SELECT COUNT(*)                AS total_ops,
                       COUNT(DISTINCT jornada) AS dias
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

            # Monto total y cantidad de premios (solo tipos premio).
            cur.execute(
                f"""
                SELECT SUM(transferencia_final) AS monto_total,
                       COUNT(*)                 AS premios
                FROM {TABLE}
                {where_tipos}
                """,
                params,
            )
            prem = cur.fetchone() or {}
            monto_total = int(prem.get("monto_total") or 0)
            premios = int(prem.get("premios") or 0)

            # Hora pico (todos los tipos): la hora con más operaciones.
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
    finally:
        conn.close()

    ops_pico = int(pico.get("ops") or 0)
    hora_pico = pico.get("hora")

    return {
        "total_ops": miles(total_ops),
        "dias": miles(dias),
        "promedio_ops": miles(round(total_ops / dias)),
        "monto_total": pesos(monto_total),
        "premios": miles(premios),
        "ticket": pesos(round(monto_total / premios)) if premios else pesos(0),
        "hora_pico": f"{hora_pico:02d}:00" if hora_pico is not None else "—",
        "ops_pico_prom": miles(round(ops_pico / dias)),
    }


def get_operaciones_por_mes(anio=None, mes=None, nombre=None):
    """Cantidad de operaciones agrupadas por mes de la jornada (TODOS los tipos).

    Devuelve {labels: ["Abril 2025", ...], valores: [123, ...]} o None.
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
    """Suma de montos por mes de la jornada (SOLO tipos premio).

    El monto es la columna transferencia_final. Devuelve {labels, valores} o None.
    """
    where, params = _where(anio, mes, nombre)
    where_tipos = _and_tipos(where)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       SUM(transferencia_final)      AS total
                FROM {TABLE}
                {where_tipos}
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

    Las operaciones usan TODOS los tipos; el monto usa SOLO los tipos premio.
    Ambos se dividen entre la cantidad de jornadas únicas del periodo (todos los
    tipos), para que "por hora" sea comparable entre periodos de distinto tamaño.

    Devuelve {labels: ["10", "11", ...], operaciones: [...], montos: [...]} en el
    orden de Jornada (10 → 08), o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    where_tipos = _and_tipos(where)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Cantidad de jornadas únicas del periodo (divisor del promedio).
            cur.execute(
                f"SELECT COUNT(DISTINCT jornada) AS n FROM {TABLE} {where}",
                params,
            )
            total_jornadas = (cur.fetchone() or {}).get("n") or 0
            if not total_jornadas:
                return None

            # Operaciones por hora (todos los tipos).
            cur.execute(
                f"""
                SELECT EXTRACT(HOUR FROM fecha)::int AS hora,
                       COUNT(*)                        AS ops
                FROM {TABLE}
                {where}
                GROUP BY 1
                """,
                params,
            )
            ops_hora = {f["hora"]: int(f["ops"]) for f in cur.fetchall()}

            # Monto por hora (solo tipos premio).
            cur.execute(
                f"""
                SELECT EXTRACT(HOUR FROM fecha)::int AS hora,
                       SUM(transferencia_final)        AS monto
                FROM {TABLE}
                {where_tipos}
                GROUP BY 1
                """,
                params,
            )
            monto_hora = {f["hora"]: int(f["monto"] or 0) for f in cur.fetchall()}
    finally:
        conn.close()

    labels, operaciones, montos = [], [], []
    for h in HORAS_JORNADA:
        labels.append(f"{h:02d}")
        operaciones.append(round(ops_hora.get(h, 0) / total_jornadas, 1))
        montos.append(round(monto_hora.get(h, 0) / total_jornadas))
    return {"labels": labels, "operaciones": operaciones, "montos": montos}


def get_heatmap_dia_hora(anio=None, mes=None, nombre=None):
    """Mapa de calor: promedio de operaciones por jornada en cada franja día×hora.

    Usa TODOS los tipos de pago. Cada celda = total de operaciones de ese
    (día de semana × hora) ÷ cantidad de jornadas únicas de ese día de la semana.

    Devuelve un dict con horas, dias, matriz, jornadas_por_dia, total_jornadas,
    rango_inicio, rango_fin; o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
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
# Todas estas funciones usan _where_record(): los filtros de año, mes y nombre,
# MÁS la exclusión de filas sin slot_attendant (no se atribuyen a nadie). Usan
# TODOS los tipos de pago: aquí se cuentan transacciones, no montos.

_MESES_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _where_record(anio=None, mes=None, nombre=None):
    """WHERE de las tablas de Record: filtros comunes + slot_attendant presente."""
    where, params = _where(anio, mes, nombre)
    cond = "slot_attendant IS NOT NULL AND TRIM(slot_attendant) <> ''"
    where = (where + " AND " + cond) if where else "WHERE " + cond
    return where, params


def get_record_jornadas(anio=None, mes=None, nombre=None):
    """Record de transacciones en UNA jornada por cada asistente.

    Para cada slot attendant busca la jornada donde hizo más transacciones (su
    mejor día). Devuelve una lista de dicts {nombre, ops, fecha} ordenada de
    mayor a menor, o [] si no hay datos.
    """
    where, params = _where_record(anio, mes, nombre)
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


def get_resumen_asistentes_tipos(anio=None, mes=None, nombre=None):
    """Resumen por asistente con conteo por tipo de pago (sin montos).

    Las columnas de tipo de pago son dinámicas: una por cada tipo presente en el
    filtro. Para cada asistente entrega el conteo por tipo, el total y su mejor
    jornada (nº de transacciones y fecha).

    Devuelve un dict:
        {
          "tipos": ["Jackpot HP", "Progressive Jackpot HP", ...],
          "filas": [{"nombre", "valores": [ints alineados a tipos], "total",
                     "mejor_ops", "mejor_fecha"}, ...],
          "totales": [ints por tipo],
          "total": N
        }
    o None si no hay datos. Las filas se ordenan por total desc.
    """
    where, params = _where_record(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Conteo por asistente y tipo de pago.
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre,
                       COALESCE(NULLIF(TRIM(tipo_de_pago), ''), 'Sin tipo') AS tipo,
                       COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant, tipo
                """,
                params,
            )
            conteos = cur.fetchall()
            if not conteos:
                return None

            # Mejor jornada por asistente.
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

    # Tipos presentes (ordenados por total descendente para columnas estables).
    total_por_tipo = {}
    por_asistente = {}
    for c in conteos:
        ops = int(c["ops"])
        total_por_tipo[c["tipo"]] = total_por_tipo.get(c["tipo"], 0) + ops
        por_asistente.setdefault(c["nombre"], {})[c["tipo"]] = ops

    tipos = sorted(total_por_tipo.keys(), key=lambda t: total_por_tipo[t], reverse=True)
    idx = {t: i for i, t in enumerate(tipos)}

    filas = []
    for nom, conteo in por_asistente.items():
        valores = [0] * len(tipos)
        for t, ops in conteo.items():
            valores[idx[t]] = ops
        mj = mejor.get(nom)
        filas.append(
            {
                "nombre": nom,
                "valores": valores,
                "total": sum(valores),
                "mejor_ops": mj["ops"] if mj else 0,
                "mejor_fecha": fecha_corta(mj["jornada"]) if mj else "—",
            }
        )
    filas.sort(key=lambda r: r["total"], reverse=True)

    totales = [total_por_tipo[t] for t in tipos]
    return {
        "tipos": tipos,
        "filas": filas,
        "totales": totales,
        "total": sum(totales),
    }


def get_transacciones_mes_anio(anio=None, mes=None, nombre=None):
    """Transacciones por mes de cada asistente, separadas por año.

    Devuelve una lista de años (de mayor a menor), cada uno con su tabla
    {anio, meses, filas:[{nombre, valores:[12], total}], totales:[12], total},
    o [] si no hay datos. Las filas se ordenan por total del año desc.
    """
    where, params = _where_record(anio, mes, nombre)
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
                "meses": _MESES_ABBR,
                "filas": filas_out,
                "totales": totales,
                "total": sum(totales),
            }
        )
    return resultado


def get_total_por_anio(anio=None, mes=None, nombre=None):
    """Total acumulado de transacciones por asistente y año (últimos 5 años).

    Las columnas son SIEMPRE los últimos 5 años (año actual y los 4 anteriores),
    aunque algunos no tengan datos (se muestran en 0). Devuelve un dict
    {anios, filas:[{nombre, valores, total}], totales, total} o None.
    """
    where, params = _where_record(anio, mes, nombre)
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

    anio_actual = datetime.now().year
    anios = list(range(anio_actual - 4, anio_actual + 1))
    idx = {a: i for i, a in enumerate(anios)}

    por_nombre = {}
    for f in filas:
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


def get_distribucion_tipos(anio=None, mes=None, nombre=None):
    """Distribución de transacciones por tipo de pago (conteo, sin montos).

    Usa _where_record (excluye filas sin asistente). Devuelve {labels, valores}
    ordenado de mayor a menor, o None si no hay datos.
    """
    where, params = _where_record(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(tipo_de_pago), ''), 'Sin tipo') AS tipo,
                       COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY tipo
                ORDER BY ops DESC
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None
    return {
        "labels": [f["tipo"] for f in filas],
        "valores": [int(f["ops"]) for f in filas],
    }


# ---------------------------------------------------------------------------
# HISTÓRICO — resumen mensual, operaciones por hora y conteo anual
# ---------------------------------------------------------------------------
#
# REGLA DE FILTRADO POR TIPO DE PAGO (igual que el dashboard):
#   - Resumen mensual: operaciones y monto SOLO de los tipos premio (_FILTRO_TIPOS).
#   - Operaciones por hora: operaciones de TODOS los tipos; monto SOLO premios.
#   - Conteo anual: conteo por tipo con TODOS los tipos (columnas dinámicas);
#     el monto de la última columna es SOLO de los tipos premio.


def get_resumen_mensual(anio=None, mes=None, nombre=None):
    """Resumen mensual del Histórico de Premios (SOLO tipos premio).

    Agrupa por mes de la jornada. Operaciones y monto cuentan solo los premios
    (Jackpot HP / Progressive Jackpot HP). Devuelve un dict:
        {"filas": [{"mes", "ops", "monto"}, ...],
         "total_ops": ..., "total_monto": ...}
    o None si no hay datos. Las filas van de más reciente a más antiguo.
    """
    where, params = _where(anio, mes, nombre)
    where_tipos = _and_tipos(where)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       COUNT(*)                      AS ops,
                       SUM(transferencia_final)      AS monto
                FROM {TABLE}
                {where_tipos}
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
            }
        )
    return {
        "filas": out,
        "total_ops": miles(total_ops),
        "total_monto": pesos(total_monto),
    }


def get_operaciones_por_hora(anio=None, mes=None, nombre=None):
    """Detalle del Histórico por hora: totales y promedios por jornada.

    Operaciones usan TODOS los tipos; el monto usa SOLO los tipos premio. Los
    promedios dividen el total entre la cantidad de jornadas únicas del periodo
    (todos los tipos). Devuelve un dict:
        {"filas": [{"hora", "ops", "ops_prom", "monto", "monto_prom",
                    "es_pico"}, ...],
         "jornadas", "total_ops", "ops_prom", "total_monto", "monto_prom"}
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    where_tipos = _and_tipos(where)
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

            # Operaciones por hora (todos los tipos).
            cur.execute(
                f"""
                SELECT EXTRACT(HOUR FROM fecha)::int AS hora,
                       COUNT(*)                        AS ops
                FROM {TABLE}
                {where}
                GROUP BY 1
                """,
                params,
            )
            ops_hora = {f["hora"]: int(f["ops"]) for f in cur.fetchall()}

            # Monto por hora (solo tipos premio).
            cur.execute(
                f"""
                SELECT EXTRACT(HOUR FROM fecha)::int AS hora,
                       SUM(transferencia_final)        AS monto
                FROM {TABLE}
                {where_tipos}
                GROUP BY 1
                """,
                params,
            )
            monto_hora = {f["hora"]: int(f["monto"] or 0) for f in cur.fetchall()}
    finally:
        conn.close()

    # Hora pico = la de mayor número de operaciones (para resaltarla).
    hora_pico = None
    max_ops = -1
    for h, ops in ops_hora.items():
        if ops > max_ops:
            max_ops = ops
            hora_pico = h

    filas = []
    total_ops = total_monto = 0
    for h in HORAS_JORNADA:
        ops = ops_hora.get(h, 0)
        monto = monto_hora.get(h, 0)
        total_ops += ops
        total_monto += monto
        filas.append(
            {
                "hora": f"{h:02d}:00",
                "ops": miles(ops),
                "ops_prom": round(ops / jornadas, 1),
                "monto": pesos(monto),
                "monto_prom": pesos(round(monto / jornadas)),
                "es_pico": h == hora_pico and ops > 0,
            }
        )
    return {
        "filas": filas,
        "jornadas": miles(jornadas),
        "total_ops": miles(total_ops),
        "ops_prom": round(total_ops / jornadas, 1),
        "total_monto": pesos(total_monto),
        "monto_prom": pesos(round(total_monto / jornadas)),
    }


def get_conteo_maquina_tipo(anio=None, mes=None, nombre=None):
    """Conteo por Mes × Máquina, con columnas dinámicas por tipo de pago.

    Cada fila es una combinación (mes de jornada, máquina). Las columnas de tipo
    de pago son dinámicas (conteo, TODOS los tipos). La última columna es el
    monto de premios (SOLO Jackpot HP / Progressive Jackpot HP). Respeta el
    filtro de año/mes del header.

    Devuelve un dict:
        {"tipos": [...],
         "filas": [{"mes", "maquina", "valores": [ints], "total", "monto"}, ...],
         "totales": [ints por tipo], "total", "total_monto"}
    o None si no hay datos. Las filas se ordenan por mes desc y luego máquina.
    """
    where, params = _where(anio, mes, nombre)
    where_tipos = _and_tipos(where)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Conteo por mes, máquina y tipo (todos los tipos).
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       COALESCE(NULLIF(TRIM(maquina), ''), 'Sin máquina') AS maquina,
                       COALESCE(NULLIF(TRIM(tipo_de_pago), ''), 'Sin tipo') AS tipo,
                       COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY 1, 2, 3
                """,
                params,
            )
            conteos = cur.fetchall()
            if not conteos:
                return None

            # Monto de premios por mes y máquina (solo tipos premio).
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', jornada) AS mes,
                       COALESCE(NULLIF(TRIM(maquina), ''), 'Sin máquina') AS maquina,
                       SUM(transferencia_final) AS monto
                FROM {TABLE}
                {where_tipos}
                GROUP BY 1, 2
                """,
                params,
            )
            montos = {(m["mes"], m["maquina"]): int(m["monto"] or 0)
                      for m in cur.fetchall()}
    finally:
        conn.close()

    # Tipos presentes, ordenados por total descendente (columnas estables).
    total_por_tipo = {}
    por_fila = {}
    for c in conteos:
        clave = (c["mes"], c["maquina"])
        ops = int(c["ops"])
        total_por_tipo[c["tipo"]] = total_por_tipo.get(c["tipo"], 0) + ops
        por_fila.setdefault(clave, {})[c["tipo"]] = ops

    tipos = sorted(total_por_tipo.keys(), key=lambda t: total_por_tipo[t], reverse=True)
    idx = {t: i for i, t in enumerate(tipos)}

    filas = []
    total_general = 0
    total_monto = 0
    for (mes_dt, maquina) in sorted(por_fila.keys(), key=lambda k: (k[0], k[1]), reverse=True):
        conteo = por_fila[(mes_dt, maquina)]
        valores = [0] * len(tipos)
        for t, ops in conteo.items():
            valores[idx[t]] = ops
        fila_total = sum(valores)
        monto = montos.get((mes_dt, maquina), 0)
        total_general += fila_total
        total_monto += monto
        filas.append(
            {
                "mes": mes_anio_es(mes_dt),
                "maquina": maquina,
                "valores": valores,
                "total": fila_total,
                "monto": pesos(monto),
            }
        )

    totales = [total_por_tipo[t] for t in tipos]
    return {
        "tipos": tipos,
        "filas": filas,
        "totales": totales,
        "total": total_general,
        "total_monto": pesos(total_monto),
    }
