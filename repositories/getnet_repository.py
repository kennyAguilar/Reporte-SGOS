"""Módulo Getnet (tabla public.getnet).

Columnas reales: id, id_unico (unique), jornada (date), fecha (timestamp),
monto (integer), slot_attendant, forma_pago, created_at.
"""
from datetime import datetime, timedelta
import unicodedata

from psycopg2.extras import execute_values

from core.database import get_connection
from core.formato import (
    fecha_corta, fecha_hora, mes_anio_es, mes_ingles, miles, pesos, porcentaje, variacion,
)

TABLE = "getnet"

# Excluye de TODAS las estadísticas de Getnet a los slot attendants marcados
# como inactivos en el apartado de Configuración. Los que no están en la tabla
# `slot_attendants` se consideran activos por defecto. Se usa NOT EXISTS para
# que la consulta no falle aunque la tabla aún no exista (LEFT semantics).
_FILTRO_ACTIVOS = (
    "slot_attendant NOT IN "
    "(SELECT nombre FROM slot_attendants WHERE activo = false)"
)

# Operaciones sin asistente asignado (celda vacía en el Excel). Se excluyen
# solo de las métricas POR asistente; los totales del dashboard las incluyen.
_FILTRO_CON_ASISTENTE = "NULLIF(TRIM(slot_attendant), '') IS NOT NULL"

# Etiquetas canónicas de forma de pago. El Excel trae variantes sin tilde o en
# inglés ("Debito", "DEBIT"); aquí se unifican para la visualización.
_FORMAS_CANON = {
    "debito": "Débito", "debit": "Débito", "td": "Débito",
    "credito": "Crédito", "credit": "Crédito", "tc": "Crédito",
}


def _sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def etiqueta_forma(valor):
    """Normaliza la forma de pago para mostrarla: 'debito' -> 'Débito'."""
    texto = (valor or "").strip()
    if not texto:
        return "Sin especificar"
    return _FORMAS_CANON.get(_sin_tildes(texto).lower(), texto)


def es_debito(valor):
    return etiqueta_forma(valor) == "Débito"


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
    where, params = _where(anio, mes, nombre)

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
                "total_label_titulo": "Monto total del mes" if mes else "Monto total acumulado",
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


def _where(anio=None, mes=None, nombre=None, solo_con_asistente=False):
    """Arma la cláusula WHERE de filtros reutilizable para los gráficos.

    Devuelve (where_sql, params). El filtro de año y mes usa `jornada`; el de
    nombre busca en `slot_attendant`. Con `solo_con_asistente=True` se dejan
    fuera las operaciones sin asistente (para rankings por persona).
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
    if solo_con_asistente:
        filtros.append(_FILTRO_CON_ASISTENTE)
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    return where, params


def get_anios_disponibles():
    """Años con operaciones cargadas, de más reciente a más antiguo."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT EXTRACT(YEAR FROM jornada)::int AS anio "
                f"FROM {TABLE} ORDER BY 1 DESC"
            )
            return [int(f["anio"]) for f in cur.fetchall()]
    finally:
        conn.close()


def _variacion_mensual(cur, nombre, max_jornada):
    """Compara el último mes con datos contra el mes calendario anterior.

    Ignora el filtro de mes (si no, el mes anterior nunca entraría) pero respeta
    nombre y activos. Devuelve {"ops": variacion, "monto": variacion,
    "mes_ref": "Septiembre 2026", "mes_prev": "Agosto 2026"} o None.
    """
    if not max_jornada:
        return None
    mes_ref = max_jornada.replace(day=1)
    mes_prev = (mes_ref - timedelta(days=1)).replace(day=1)

    where, params = _where(None, None, nombre)
    cur.execute(
        f"""
        SELECT DATE_TRUNC('month', jornada)::date AS mes,
               COUNT(*)   AS ops,
               SUM(monto) AS monto
        FROM {TABLE}
        {where} AND DATE_TRUNC('month', jornada)::date IN (%s, %s)
        GROUP BY 1
        """,
        params + [mes_ref, mes_prev],
    )
    por_mes = {f["mes"]: f for f in cur.fetchall()}
    actual = por_mes.get(mes_ref)
    anterior = por_mes.get(mes_prev)
    if not actual or not anterior:
        return None
    return {
        "ops": variacion(int(actual["ops"]), int(anterior["ops"])),
        "monto": variacion(int(actual["monto"] or 0), int(anterior["monto"] or 0)),
        "mes_ref": mes_anio_es(mes_ref),
        "mes_prev": mes_anio_es(mes_prev),
    }


# Colores de las formas de pago para el donut (consistentes con DESIGN.md).
_COLORES_FORMA = ["#d4af37", "#24a148", "#78a9ff", "#ff832b", "#be95ff", "#08bdba"]


def get_kpis_dashboard(anio=None, mes=None, nombre=None):
    """KPIs resumidos para las tarjetas del dashboard.

    Devuelve un dict con:
        - total_ops, dias, promedio_ops
        - monto_total, ticket
        - hora_pico ("HH:00"), ops_pico_prom
        - formas: [{"label", "ops", "monto", "pct", "color"}, ...] para el donut
        - variacion: {"ops", "monto", "mes_ref", "mes_prev"} último mes vs anterior
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
                       SUM(monto)              AS monto_total,
                       MAX(jornada)            AS max_jornada
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
            variacion_mes = _variacion_mensual(cur, nombre, base.get("max_jornada"))

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

    # Se agrupa por etiqueta canónica: "Debito" y "Débito" suman juntas.
    acumulado = {}
    for f in filas_forma:
        etiqueta = etiqueta_forma(f["forma"])
        acc = acumulado.setdefault(etiqueta, {"ops": 0, "monto": 0})
        acc["ops"] += int(f["ops"])
        acc["monto"] += int(f["monto"] or 0)

    formas = []
    for i, (etiqueta, acc) in enumerate(
        sorted(acumulado.items(), key=lambda kv: kv[1]["ops"], reverse=True)
    ):
        formas.append(
            {
                "label": etiqueta,
                "ops": acc["ops"],
                "monto": acc["monto"],
                "pct": round(acc["ops"] * 100 / total_ops, 1),
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
        "variacion": variacion_mes,
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

    # Variación contra el mes anterior en la lista (las filas vienen DESC, así
    # que el "anterior" cronológico es el siguiente elemento).
    out = []
    total_ops = total_monto = 0
    for i, f in enumerate(filas):
        ops = int(f["ops"])
        monto = int(f["monto"] or 0)
        total_ops += ops
        total_monto += monto
        prev = filas[i + 1] if i + 1 < len(filas) else None
        es_consecutivo = prev is not None and (
            (f["mes"].year - prev["mes"].year) * 12 + f["mes"].month - prev["mes"].month == 1
        )
        out.append(
            {
                "mes": mes_anio_es(f["mes"]),
                "ops": miles(ops),
                "monto": pesos(monto),
                "ticket": pesos(round(monto / ops)) if ops else pesos(0),
                "delta_ops": variacion(ops, int(prev["ops"])) if es_consecutivo else None,
                "delta_monto": variacion(monto, int(prev["monto"] or 0)) if es_consecutivo else None,
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
# RECORD ASISTENTES — métricas operativas por slot attendant
# ---------------------------------------------------------------------------
#
# Todas estas funciones usan _where(..., solo_con_asistente=True): aplican los
# filtros de año, mes y nombre, excluyen a los inactivos de Configuración y
# dejan fuera las operaciones sin asistente asignado.
#
# Reglas de desempate (para que el resultado sea siempre el mismo):
#   - Mejor jornada: más operaciones; si empatan, la jornada más reciente.
#   - Franja top:    más operaciones; si empatan, la hora más temprana en el
#                    orden de Jornada (10 → 08).
#   - Rankings:      más operaciones; si empatan, nombre alfabético.

_MESES_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
_ORDEN_HORA = {h: i for i, h in enumerate(HORAS_JORNADA)}


def _consultar_por_asistente(cur, where, params):
    """Ejecuta las tres consultas base por asistente y devuelve dicts crudos.

    Devuelve (base, por_jornada, por_hora):
      - base[nombre]        = {"total", "monto", "jornadas"}
      - por_jornada[nombre] = [(jornada, ops, monto), ...]
      - por_hora[nombre]    = {hora: ops}
    """
    cur.execute(
        f"""
        SELECT slot_attendant          AS nombre,
               COUNT(*)                AS total,
               SUM(monto)              AS monto,
               COUNT(DISTINCT jornada) AS jornadas
        FROM {TABLE}
        {where}
        GROUP BY slot_attendant
        """,
        params,
    )
    base = {f["nombre"]: dict(f) for f in cur.fetchall()}
    if not base:
        return {}, {}, {}

    cur.execute(
        f"""
        SELECT slot_attendant AS nombre, jornada, COUNT(*) AS ops, SUM(monto) AS monto
        FROM {TABLE}
        {where}
        GROUP BY slot_attendant, jornada
        """,
        params,
    )
    por_jornada = {}
    for f in cur.fetchall():
        por_jornada.setdefault(f["nombre"], []).append(
            (f["jornada"], int(f["ops"]), int(f["monto"] or 0))
        )

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
    por_hora = {}
    for f in cur.fetchall():
        por_hora.setdefault(f["nombre"], {})[f["hora"]] = int(f["ops"])

    return base, por_jornada, por_hora


def _mejor_jornada(jornadas):
    """(jornada, ops, monto) con más ops; empate → la más reciente."""
    if not jornadas:
        return None
    return max(jornadas, key=lambda j: (j[1], j[0]))


def _franja_top(horas):
    """Hora con más ops; empate → la más temprana en el orden de Jornada."""
    if not horas:
        return None
    return min(horas.items(), key=lambda kv: (-kv[1], _ORDEN_HORA.get(kv[0], 99)))[0]


def get_resumen_asistentes(anio=None, mes=None, nombre=None):
    """Resumen operativo por asistente, ordenado por total de transacciones.

    Cada fila trae:
      - nombre, total (int), jornadas (int), prom_jornada (float, 1 decimal)
      - franja ("HH:00")
      - mejor_ops (int), mejor_monto ("$1.234"), mejor_fecha (dd/mm/aaaa),
        mejor_fecha_iso (para ordenar en la tabla)
    Devuelve una lista o [].

    El podio de "Record en una jornada" se deriva de estas mismas filas (ver
    `ordenar_por_record`), así la página hace una sola pasada por la tabla.
    """
    where, params = _where(anio, mes, nombre, solo_con_asistente=True)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            base, por_jornada, por_hora = _consultar_por_asistente(cur, where, params)
    finally:
        conn.close()

    resultado = []
    for nom, b in base.items():
        total = int(b["total"])
        jornadas = int(b["jornadas"] or 0)
        mejor = _mejor_jornada(por_jornada.get(nom))
        franja = _franja_top(por_hora.get(nom))
        resultado.append(
            {
                "nombre": nom,
                "total": total,
                "jornadas": jornadas,
                "prom_jornada": round(total / jornadas, 1) if jornadas else 0.0,
                "franja": f"{franja:02d}:00" if franja is not None else "—",
                "mejor_ops": mejor[1] if mejor else 0,
                "mejor_monto": pesos(mejor[2]) if mejor else pesos(0),
                "mejor_fecha": fecha_corta(mejor[0]) if mejor else "—",
                "mejor_fecha_iso": mejor[0].isoformat() if mejor else "",
            }
        )
    resultado.sort(key=lambda r: (-r["total"], r["nombre"]))
    return resultado


def ordenar_por_record(resumen):
    """Ranking de records en una jornada a partir del resumen por asistente.

    Más operaciones primero; en empate gana quien lo logró antes (fecha más
    antigua) y luego el nombre.
    """
    return sorted(
        resumen,
        key=lambda r: (-r["mejor_ops"], r["mejor_fecha_iso"], r["nombre"]),
    )


def get_transacciones_mes_anio(anio=None, mes=None, nombre=None):
    """Transacciones por mes de cada asistente, separadas por año.

    Devuelve una lista de años (de mayor a menor), cada uno con su tabla. Solo
    aparecen las columnas de los meses que tienen datos en ese año:
        [
          {
            "anio": 2026,
            "meses": ["Ene", "Feb", ...],
            "filas": [{"nombre": ..., "valores": [...], "total": N}, ...],
            "totales": [...],   # total por mes (pie de tabla)
            "total": N          # total del año
          }, ...
        ]
    o [] si no hay datos. Las filas se ordenan por total del año desc.
    """
    where, params = _where(anio, mes, nombre, solo_con_asistente=True)
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

    # estructura: anios[anio][nombre] = {mes: ops}
    anios = {}
    for f in filas:
        a = anios.setdefault(f["anio"], {})
        a.setdefault(f["nombre"], {})[f["mes"]] = int(f["ops"])

    resultado = []
    for a in sorted(anios.keys(), reverse=True):
        asistentes = anios[a]
        meses_con_datos = sorted({m for vals in asistentes.values() for m in vals})
        filas_out = []
        for nom, vals in asistentes.items():
            valores = [vals.get(m, 0) for m in meses_con_datos]
            filas_out.append({"nombre": nom, "valores": valores, "total": sum(valores)})
        filas_out.sort(key=lambda r: (-r["total"], r["nombre"]))
        totales = [sum(f["valores"][i] for f in filas_out) for i in range(len(meses_con_datos))]
        resultado.append(
            {
                "anio": a,
                "meses": [_MESES_ABBR[m - 1] for m in meses_con_datos],
                "filas": filas_out,
                "totales": totales,
                "total": sum(totales),
            }
        )
    return resultado


def get_total_por_anio(anio=None, mes=None, nombre=None):
    """Total acumulado de transacciones por asistente y año.

    Las columnas son los años que tienen datos en el filtro (ascendente), así
    la tabla no muestra columnas vacías ni descarta años antiguos.

    Devuelve un dict:
        {
          "anios": [2025, 2026],
          "filas": [{"nombre": ..., "valores": [...], "total": N}, ...],
          "totales": [...],
          "total": N
        }
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre, solo_con_asistente=True)
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

    anios = sorted({f["anio"] for f in filas})
    idx = {a: i for i, a in enumerate(anios)}

    por_nombre = {}
    for f in filas:
        vals = por_nombre.setdefault(f["nombre"], [0] * len(anios))
        vals[idx[f["anio"]]] = int(f["ops"])

    filas_out = [
        {"nombre": nom, "valores": vals, "total": sum(vals)}
        for nom, vals in por_nombre.items()
    ]
    filas_out.sort(key=lambda r: (-r["total"], r["nombre"]))
    totales = [sum(por_nombre[nom][i] for nom in por_nombre) for i in range(len(anios))]

    return {
        "anios": anios,
        "filas": filas_out,
        "totales": totales,
        "total": sum(totales),
    }


# ---------------------------------------------------------------------------
# RENDIMIENTO — evaluación de desempeño por asistente
# ---------------------------------------------------------------------------
#
# La métrica principal es la CANTIDAD DE OPERACIONES. Para que la comparación
# sea justa entre asistentes con distinta asistencia, todo se normaliza por
# jornadas trabajadas:
#
#   - Prom./jornada      = transacciones ÷ jornadas en que operó.
#   - Promedio del equipo = total de transacciones ÷ total de pares
#                           (asistente, jornada). Es el "ritmo" medio por persona
#                           y día.
#   - Índice vs equipo    = prom./jornada del asistente ÷ promedio del equipo
#                           × 100. 100 = igual al equipo.
#   - Cobertura           = jornadas del asistente ÷ jornadas del periodo.
#   - Constancia          = % de sus jornadas en que igualó o superó el
#                           promedio del equipo.
#   - Tendencia           = variación de sus transacciones entre los dos últimos
#                           meses con datos del periodo.
#
# El monto, el ticket y el % de débito se muestran como contexto secundario.

# Jornadas mínimas para entrar al ranking de promedio por jornada (evita que
# alguien con un solo día destacado lidere la tabla).
_MIN_JORNADAS_RANKING = 5


def _mediana(valores):
    if not valores:
        return 0
    v = sorted(valores)
    n = len(v)
    mitad = n // 2
    return v[mitad] if n % 2 else (v[mitad - 1] + v[mitad]) / 2


def get_rendimiento_asistentes(anio=None, mes=None, nombre=None):
    """Evaluación de desempeño por asistente.

    Devuelve un dict con:
      - kpis:  {asistentes, jornadas_periodo, prom_por_asistente, mediana,
                prom_equipo, lider, lider_prom, top3_pct, top1, top1_pct}
      - filas: lista ordenada por transacciones (desc), cada una con las
               métricas descritas en el encabezado de esta sección, ya
               formateadas para la tabla, más `ops_raw` para los gráficos.
      - totales: fila de pie {ops, jornadas, prom_jornada, monto, ticket, debito_pct}
      - top_ops:  {labels, valores} Top 10 por transacciones
      - top_prom: {labels, valores} Top 10 por prom./jornada (min. jornadas)
      - min_jornadas: umbral usado en top_prom
      - tendencia: {"mes_ref", "mes_prev"} o None si no hay dos meses
    o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre, solo_con_asistente=True)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            base, por_jornada, _ = _consultar_por_asistente(cur, where, params)
            if not base:
                return None

            cur.execute(
                f"SELECT COUNT(DISTINCT jornada) AS n FROM {TABLE} {where}",
                params,
            )
            jornadas_periodo = int((cur.fetchone() or {}).get("n") or 0)

            # Operaciones por forma de pago (para % débito).
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre, forma_pago, COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant, forma_pago
                """,
                params,
            )
            debito = {}
            for f in cur.fetchall():
                if es_debito(f["forma_pago"]):
                    debito[f["nombre"]] = debito.get(f["nombre"], 0) + int(f["ops"])

            # Operaciones por mes para la tendencia (dos últimos meses).
            cur.execute(
                f"""
                SELECT slot_attendant AS nombre,
                       DATE_TRUNC('month', jornada)::date AS mes,
                       COUNT(*) AS ops
                FROM {TABLE}
                {where}
                GROUP BY slot_attendant, mes
                """,
                params,
            )
            por_mes = {}
            meses = set()
            for f in cur.fetchall():
                meses.add(f["mes"])
                por_mes.setdefault(f["nombre"], {})[f["mes"]] = int(f["ops"])
    finally:
        conn.close()

    total_ops = sum(int(b["total"]) for b in base.values())
    total_monto = sum(int(b["monto"] or 0) for b in base.values())
    total_pares = sum(len(j) for j in por_jornada.values())
    prom_equipo = total_ops / total_pares if total_pares else 0

    meses_orden = sorted(meses)
    mes_ref = meses_orden[-1] if len(meses_orden) >= 2 else None
    mes_prev = meses_orden[-2] if len(meses_orden) >= 2 else None

    filas = []
    for nom, b in base.items():
        ops = int(b["total"])
        monto = int(b["monto"] or 0)
        jornadas = int(b["jornadas"] or 0)
        prom = ops / jornadas if jornadas else 0
        indice = prom * 100 / prom_equipo if prom_equipo else 0
        mejor = _mejor_jornada(por_jornada.get(nom))
        sobre_prom = sum(1 for j in por_jornada.get(nom, []) if j[1] >= prom_equipo)

        tendencia = None
        if mes_ref:
            m = por_mes.get(nom, {})
            tendencia = variacion(m.get(mes_ref, 0), m.get(mes_prev, 0))
            if tendencia is None and m.get(mes_ref, 0) and not m.get(mes_prev, 0):
                tendencia = {"pct": "nuevo", "dir": "flat"}

        filas.append(
            {
                "nombre": nom,
                "ops_raw": ops,
                "prom_raw": round(prom, 1),
                "jornadas_raw": jornadas,
                "ops": miles(ops),
                "pct_total": porcentaje(ops, total_ops),
                "jornadas": miles(jornadas),
                "cobertura": porcentaje(jornadas, jornadas_periodo, 0),
                "prom_jornada": f"{prom:.1f}".replace(".", ","),
                "indice": round(indice),
                "constancia": porcentaje(sobre_prom, jornadas, 0),
                "mejor_ops": mejor[1] if mejor else 0,
                "tendencia": tendencia,
                "monto": pesos(monto),
                "ticket": pesos(round(monto / ops)) if ops else pesos(0),
                "debito_pct": porcentaje(debito.get(nom, 0), ops, 0),
            }
        )
    filas.sort(key=lambda r: (-r["ops_raw"], r["nombre"]))

    # KPIs del equipo.
    n_asist = len(filas)
    ops_list = [f["ops_raw"] for f in filas]
    lider = max(filas, key=lambda r: (r["prom_raw"], r["ops_raw"]))
    top3 = sum(ops_list[:3])

    min_jornadas = min(_MIN_JORNADAS_RANKING, jornadas_periodo) or 1
    elegibles = [f for f in filas if f["jornadas_raw"] >= min_jornadas]
    elegibles.sort(key=lambda r: (-r["prom_raw"], -r["ops_raw"], r["nombre"]))

    total_debito = sum(debito.values())
    return {
        "kpis": {
            "asistentes": miles(n_asist),
            "jornadas_periodo": miles(jornadas_periodo),
            "prom_por_asistente": miles(round(total_ops / n_asist)) if n_asist else "0",
            "mediana": miles(round(_mediana(ops_list))),
            "prom_equipo": f"{prom_equipo:.1f}".replace(".", ","),
            "lider": lider["nombre"],
            "lider_prom": lider["prom_jornada"],
            "top3_pct": porcentaje(top3, total_ops),
            "top1": filas[0]["nombre"],
            "top1_pct": filas[0]["pct_total"],
        },
        "filas": filas,
        "totales": {
            "ops": miles(total_ops),
            "jornadas": miles(jornadas_periodo),
            "prom_jornada": f"{prom_equipo:.1f}".replace(".", ","),
            "monto": pesos(total_monto),
            "ticket": pesos(round(total_monto / total_ops)) if total_ops else pesos(0),
            "debito_pct": porcentaje(total_debito, total_ops, 0),
        },
        "top_ops": {
            "labels": [f["nombre"] for f in filas[:10]],
            "valores": [f["ops_raw"] for f in filas[:10]],
        },
        "top_prom": {
            "labels": [f["nombre"] for f in elegibles[:10]],
            "valores": [f["prom_raw"] for f in elegibles[:10]],
        },
        "min_jornadas": min_jornadas,
        "tendencia": (
            {"mes_ref": mes_anio_es(mes_ref), "mes_prev": mes_anio_es(mes_prev)}
            if mes_ref else None
        ),
    }
