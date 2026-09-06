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
from core.formato import fecha_hora, fecha_larga, mes_anio_es, mes_ingles, miles, pesos

from psycopg2.extras import execute_values

TABLE = "comps"

# Nombres de día de la semana. PostgreSQL EXTRACT(DOW): 0=domingo ... 6=sábado.
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
# Mapa DOW de PostgreSQL -> índice 0..6 con Lunes primero.
_DOW_A_INDICE = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 0: 6}

# Colores para el donut de categorías (consistentes con DESIGN.md).
_COLORES_CAT = ["#d4af37", "#24a148", "#78a9ff", "#ff832b", "#be95ff", "#08bdba", "#fa4d56"]


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
    Usamos ON CONFLICT (id_unico) DO UPDATE: si el id_unico ya existe se
    refrescan sus valores en vez de ignorarlo. Así, volver a cargar un mes ya
    cargado corrige registros mal parseados (por ejemplo, los `cliente_id` que
    quedaron en notación científica) sin tener que borrar la tabla.

    `RETURNING (xmax = 0)` distingue las filas nuevas de las actualizadas:
    en una inserción real xmax vale 0.

    Devuelve un dict con: inserted (nuevas) y skipped (ya existían y se
    actualizaron).
    """
    if not filas:
        return {"inserted": 0, "skipped": 0}
    # ON CONFLICT DO UPDATE no admite tocar la misma fila dos veces en un
    # mismo INSERT, así que dejamos una sola aparición por id_unico (la última).
    unicas = {f["id_unico"]: f for f in filas}
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
            resultado = execute_values(
                cur,
                f"""
                INSERT INTO {TABLE}
                    (id_unico, fecha_real, fecha_jornada, cliente_id,
                     nombre_cliente, descripcion_cat, descripcion_prod,
                     micros, estado, usuario_id, nombre)
                VALUES %s
                ON CONFLICT (id_unico) DO UPDATE SET
                    fecha_real       = EXCLUDED.fecha_real,
                    fecha_jornada    = EXCLUDED.fecha_jornada,
                    cliente_id       = EXCLUDED.cliente_id,
                    nombre_cliente   = EXCLUDED.nombre_cliente,
                    descripcion_cat  = EXCLUDED.descripcion_cat,
                    descripcion_prod = EXCLUDED.descripcion_prod,
                    micros           = EXCLUDED.micros,
                    estado           = EXCLUDED.estado,
                    usuario_id       = EXCLUDED.usuario_id,
                    nombre           = EXCLUDED.nombre
                RETURNING (xmax = 0) AS nueva
                """,
                valores,
                fetch=True,
            )
            inserted = sum(1 for r in resultado if r["nueva"])
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
                "total_label_titulo": "Micros totales del mes" if mes else "Micros totales acumulados",
                "total_valor": miles(r["micros_total"]),
                "total_label": f"{miles(r['cantidad'])} comps",
                "ultima_valor": miles(u.get("m")),
                "ultima_label": f"{miles(u.get('c'))} comps · {fecha_larga(max_jornada)}",
            }
    finally:
        conn.close()


def _where(anio=None, mes=None, nombre=None):
    """Arma la cláusula WHERE de filtros reutilizable para los gráficos.

    Devuelve (where_sql, params). El filtro de año y mes usa `fecha_jornada`;
    el de nombre busca en `nombre_cliente` o `nombre`. Sin filtros, where_sql es "".
    """
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
    return where, params


def get_kpis_dashboard(anio=None, mes=None, nombre=None):
    """KPIs resumidos para las tarjetas del dashboard de Comps.

    Devuelve un dict con:
        - total_comps, dias, promedio_comps (cortesías por jornada)
        - monto_total (suma de micros), ticket (micros promedio por cortesía)
        - clientes_unicos
    o None si no hay datos en el filtro. Los promedios usan la cantidad de
    jornadas únicas (días contados) como divisor.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)                       AS total_comps,
                       COUNT(DISTINCT fecha_jornada)  AS dias,
                       SUM(micros)                    AS monto_total,
                       COUNT(DISTINCT cliente_id)     AS clientes
                FROM {TABLE}
                {where}
                """,
                params,
            )
            base = cur.fetchone() or {}
    finally:
        conn.close()

    total_comps = int(base.get("total_comps") or 0)
    dias = int(base.get("dias") or 0)
    if not total_comps or not dias:
        return None
    monto_total = int(base.get("monto_total") or 0)
    clientes = int(base.get("clientes") or 0)

    return {
        "total_comps": miles(total_comps),
        "dias": miles(dias),
        "promedio_comps": miles(round(total_comps / dias)),
        "monto_total": miles(monto_total),
        "ticket": miles(round(monto_total / total_comps)),
        "clientes_unicos": miles(clientes),
    }


def get_cortesias_por_mes(anio=None, mes=None, nombre=None):
    """Cantidad de cortesías agrupadas por mes de la jornada.

    Devuelve {labels: ["Abril 2025", ...], valores: [123, ...]} o None.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', fecha_jornada) AS mes,
                       COUNT(*)                            AS cantidad
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
    """Suma de micros agrupada por mes de la jornada.

    Devuelve {labels: [...], valores: [micros, ...]} o None si no hay datos.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DATE_TRUNC('month', fecha_jornada) AS mes,
                       SUM(micros)                         AS total
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


def get_promedio_por_dia_semana(anio=None, mes=None, nombre=None):
    """Promedio de cortesías y micros por día de la semana.

    Para cada día (Lunes..Domingo) suma cortesías y micros, y los divide entre
    la cantidad de jornadas (fechas) únicas de ese día de la semana presentes en
    los datos. Así el promedio es comparable entre periodos de distinto tamaño.

    Devuelve {labels: ["Lunes", ...], cortesias: [...], montos: [...]} o None.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT EXTRACT(DOW FROM fecha_jornada)::int AS dow,
                       COUNT(*)                             AS cortesias,
                       SUM(micros)                          AS micros,
                       COUNT(DISTINCT fecha_jornada)        AS jornadas
                FROM {TABLE}
                {where}
                GROUP BY 1
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    cortesias = [0.0] * 7
    montos = [0.0] * 7
    hay_datos = False
    for f in filas:
        idx = _DOW_A_INDICE.get(int(f["dow"]))
        if idx is None:
            continue
        jornadas = int(f["jornadas"] or 0)
        if not jornadas:
            continue
        hay_datos = True
        cortesias[idx] = round(int(f["cortesias"]) / jornadas, 1)
        montos[idx] = round(int(f["micros"] or 0) / jornadas)

    if not hay_datos:
        return None
    return {"labels": DIAS_SEMANA, "cortesias": cortesias, "montos": montos}


def get_top_productos(anio=None, mes=None, nombre=None, limit=10):
    """Top de productos más quemados por cantidad de cortesías.

    Devuelve {labels: [...], valores: [count, ...]} (de mayor a menor) o None.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(descripcion_prod), ''), 'Sin especificar') AS prod,
                       COUNT(*) AS cantidad
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY cantidad DESC
                LIMIT %s
                """,
                params + [limit],
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None
    return {
        "labels": [f["prod"] for f in filas],
        "valores": [int(f["cantidad"]) for f in filas],
    }


def get_categorias(anio=None, mes=None, nombre=None):
    """Distribución de cortesías por categoría (para el donut).

    Devuelve {formas: [{"label", "valor", "pct", "color"}, ...]} o None.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(descripcion_cat), ''), 'Sin especificar') AS cat,
                       COUNT(*) AS cantidad
                FROM {TABLE}
                {where}
                GROUP BY 1
                ORDER BY cantidad DESC
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    total = sum(int(f["cantidad"]) for f in filas) or 1
    formas = []
    for i, f in enumerate(filas):
        valor = int(f["cantidad"])
        formas.append(
            {
                "label": f["cat"],
                "valor": valor,
                "pct": round(valor * 100 / total, 1),
                "color": _COLORES_CAT[i % len(_COLORES_CAT)],
            }
        )
    return {"formas": formas}


def get_categorias_detalle(anio=None, mes=None, nombre=None):
    """Histórico Por Categoría: cada categoría con su detalle de productos.

    Devuelve una lista (de mayor a menor monto) de categorías:
        [
          {
            "categoria": "BEBIDAS",
            "cantidad": 5834,
            "monto": 22353500,
            "productos": [
              {"producto": "Coca cola", "cantidad": 812, "monto": 2842000}, ...
            ]
          }, ...
        ]
    Los productos dentro de cada categoría van de mayor a menor monto.
    Devuelve None si no hay datos en el filtro.
    """
    where, params = _where(anio, mes, nombre)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(descripcion_cat), ''), 'Sin categoría')  AS categoria,
                       COALESCE(NULLIF(TRIM(descripcion_prod), ''), 'Sin producto')  AS producto,
                       COUNT(*)     AS cantidad,
                       SUM(micros)  AS monto
                FROM {TABLE}
                {where}
                GROUP BY 1, 2
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    cats = {}
    for f in filas:
        cat = f["categoria"]
        c = cats.setdefault(cat, {"categoria": cat, "cantidad": 0, "monto": 0, "productos": []})
        cantidad = int(f["cantidad"])
        monto = int(f["monto"] or 0)
        c["cantidad"] += cantidad
        c["monto"] += monto
        c["productos"].append(
            {
                "producto": f["producto"],
                "cantidad": cantidad,
                "cantidad_fmt": miles(cantidad),
                "monto": monto,
                "monto_fmt": pesos(monto),
            }
        )

    salida = list(cats.values())
    for c in salida:
        c["productos"].sort(key=lambda p: p["monto"], reverse=True)
        c["cantidad_fmt"] = miles(c["cantidad"])
        c["monto_fmt"] = pesos(c["monto"])
    salida.sort(key=lambda c: c["monto"], reverse=True)
    return salida


def get_resumen_jugadores(anio=None, mes=None, nombre=None):
    """Entregas: resumen por jugador con el detalle de los jefes que invitaron.

    Cada jugador (nombre_cliente) trae su total de cortesías y monto, y la
    lista de jefes que lo invitaron con su área. El jefe se cruza con la tabla
    `jefaturas` por usuario_id para obtener el área. Cuando la cortesía no tiene
    jefe (campo `nombre` en blanco) se trata de una máquina de auto atención.

    Devuelve una lista (de mayor a menor monto) de jugadores:
        [
          {
            "jugador": "JUAN PEREZ",
            "cantidad": 12, "cantidad_fmt": "12",
            "monto": 450000, "monto_fmt": "$450.000",
            "jefes": [
              {"jefe": "Pedro Soto", "area": "Caja",
               "cantidad": 8, "cantidad_fmt": "8",
               "monto": 300000, "monto_fmt": "$300.000"}, ...
            ]
          }, ...
        ]
    Devuelve None si no hay datos en el filtro.
    """
    # Filtros con columnas calificadas (hay JOIN con jefaturas que también
    # tiene una columna `nombre`, por eso no se reutiliza _where()).
    filtros, params = [], []
    if anio:
        filtros.append("EXTRACT(YEAR FROM c.fecha_jornada) = %s")
        params.append(int(anio))
    if mes:
        filtros.append("EXTRACT(MONTH FROM c.fecha_jornada) = %s")
        params.append(int(mes))
    if nombre:
        filtros.append("(c.nombre_cliente ILIKE %s OR c.nombre ILIKE %s)")
        params.append(f"%{nombre}%")
        params.append(f"%{nombre}%")
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(c.nombre_cliente), ''), 'Sin nombre') AS jugador,
                       NULLIF(TRIM(c.nombre), '')                                 AS jefe,
                       CASE WHEN NULLIF(TRIM(c.nombre), '') IS NULL THEN NULL
                            ELSE NULLIF(TRIM(j.area), '') END                      AS area,
                       COUNT(*)                                                   AS cantidad,
                       SUM(c.micros)                                              AS monto
                FROM {TABLE} c
                LEFT JOIN jefaturas j ON j.usuario_id = c.usuario_id
                {where}
                GROUP BY 1, 2, 3
                """,
                params,
            )
            filas = cur.fetchall()
    finally:
        conn.close()

    if not filas:
        return None

    jugadores = {}
    for f in filas:
        nom = f["jugador"]
        j = jugadores.setdefault(
            nom, {"jugador": nom, "cantidad": 0, "monto": 0, "jefes": []}
        )
        cantidad = int(f["cantidad"])
        monto = int(f["monto"] or 0)
        j["cantidad"] += cantidad
        j["monto"] += monto
        es_maquina = not f["jefe"]
        j["jefes"].append(
            {
                "jefe": "Auto atención" if es_maquina else f["jefe"],
                "area": "Máquina" if es_maquina else (f["area"] or "Sin área"),
                "cantidad": cantidad,
                "cantidad_fmt": miles(cantidad),
                "monto": monto,
                "monto_fmt": pesos(monto),
            }
        )

    salida = list(jugadores.values())
    for j in salida:
        j["jefes"].sort(key=lambda x: x["monto"], reverse=True)
        j["cantidad_fmt"] = miles(j["cantidad"])
        j["monto_fmt"] = pesos(j["monto"])
    salida.sort(key=lambda j: j["monto"], reverse=True)
    return salida
