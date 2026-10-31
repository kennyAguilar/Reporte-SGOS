"""Repositorio del Resumen (pantalla principal).

Reúne, en pocas consultas, lo que un jefe quiere ver al entrar:

  - Panel por módulo: métrica principal del último mes con datos, variación
    contra el mes anterior, última jornada y un semáforo de frescura.
  - Alertas: módulos rezagados, cargas antiguas, jefaturas sin área.
  - Estado de carga: última carga de cada módulo según `upload_log`.
  - Tendencia: operaciones por mes de Getnet y Premios (últimos 6 meses).

Semáforo de frescura
--------------------
Las cargas son mensuales, así que medir el atraso contra "hoy" pondría todo en
rojo casi siempre. En su lugar se mide el REZAGO de cada módulo respecto del
módulo más al día (el que tiene la última jornada más reciente):

    ok    rezago <= UMBRAL_DIAS / 2
    warn  rezago <= UMBRAL_DIAS
    bad   rezago >  UMBRAL_DIAS

Además se informan los días absolutos desde la última jornada y se alerta si
ni siquiera el módulo líder tiene datos del último mes.

Cada módulo define su propia fuente (tabla, columna de fecha, métrica y cómo
aplica el filtro Nombre). Si una tabla no existe aún, el módulo se omite.
"""
from datetime import date, timedelta

from core.database import get_connection
from core.formato import fecha_corta, fecha_hora, mes_anio_es, miles, pesos, variacion

UMBRAL_DIAS = 7

# Definición de cada módulo del panel. `nombre_sql` es el filtro que aplica
# el campo Nombre del panel de filtros (igual que en el módulo respectivo).
MODULOS = [
    {
        "clave": "getnet",
        "titulo": "Getnet",
        "tabla": "getnet",
        "fecha": "jornada",
        "metrica": "COUNT(*)",
        "monto": "SUM(monto)",
        "unidad": "operaciones",
        "nombre_sql": "slot_attendant ILIKE %s",
        "nombre_desc": "asistente",
        "extra_where": (
            "slot_attendant NOT IN (SELECT nombre FROM slot_attendants WHERE activo = false)"
        ),
        "url": "getnet.dashboard",
        "url_carga": "upload.upload",
        "upload_tipo": "getnet",
    },
    {
        "clave": "premios",
        "titulo": "Premios",
        "tabla": "premios",
        "fecha": "jornada",
        "metrica": "COUNT(*)",
        "monto": (
            "SUM(CASE WHEN tipo_de_pago IN ('Jackpot HP', 'Progressive Jackpot HP') "
            "THEN transferencia_final ELSE 0 END)"
        ),
        "unidad": "premios",
        "monto_label": "Monto HP",
        "nombre_sql": "(slot_attendant ILIKE %s OR cliente ILIKE %s)",
        "nombre_params": 2,
        "nombre_desc": "asistente o cliente",
        "extra_where": (
            "COALESCE(slot_attendant, '') NOT IN "
            "(SELECT nombre FROM slot_attendants WHERE activo = false)"
        ),
        "url": "premios.dashboard",
        "url_carga": "upload.upload_premios",
        "upload_tipo": "premios",
    },
    {
        "clave": "comps",
        "titulo": "Comps",
        "tabla": "comps",
        "fecha": "fecha_jornada",
        "metrica": "COUNT(*)",
        "monto": "SUM(micros)",
        "unidad": "cortesías",
        "monto_label": "Micros",
        "monto_formato": "miles",
        "nombre_sql": "(nombre_cliente ILIKE %s OR nombre ILIKE %s)",
        "nombre_params": 2,
        "nombre_desc": "cliente o jefe",
        "url": "comps.dashboard",
        "url_carga": "upload.upload_comps",
        "upload_tipo": "comps",
    },
    {
        "clave": "coinin_mda",
        "titulo": "Coin In MDA",
        "tabla": "coinin",
        "fecha": "jornada",
        "metrica": "COUNT(DISTINCT player_id)",
        "monto": "SUM(coin_in)",
        "unidad": "jugadores",
        "monto_label": "Coin In",
        "nombre_sql": "(full_name ILIKE %s OR player_id ILIKE %s)",
        "nombre_params": 2,
        "nombre_desc": "jugador",
        "extra_where": "sistema = 'MDA'",
        "url": "coinin.mda_dashboard",
        "url_carga": "upload.upload_coinin",
        "url_carga_args": {"sistema": "mda"},
        "upload_tipo": "coinin_mda",
    },
    {
        "clave": "coinin_mdj",
        "titulo": "Coin In MDJ",
        "tabla": "mesas",
        "fecha": "fecha_operacion",
        "metrica": "COUNT(DISTINCT id_cliente)",
        "monto": "SUM(coin_in)",
        "unidad": "jugadores",
        "monto_label": "Coin In",
        "nombre_sql": "(nombre ILIKE %s OR id_cliente ILIKE %s)",
        "nombre_params": 2,
        "nombre_desc": "jugador",
        "url": "coinin.mdj_dashboard",
        "url_carga": "upload.upload_mesas",
        "upload_tipo": "mesas",
    },
]


def _tabla_existe(cur, tabla):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL AS existe", (f"public.{tabla}",))
    return bool((cur.fetchone() or {}).get("existe"))


def _where_modulo(m, anio=None, nombre=None):
    """WHERE del módulo con año y nombre (el mes se resuelve sobre la serie)."""
    filtros, params = [], []
    if anio:
        filtros.append(f"EXTRACT(YEAR FROM {m['fecha']}) = %s")
        params.append(int(anio))
    if nombre:
        filtros.append(m["nombre_sql"])
        params.extend([f"%{nombre}%"] * m.get("nombre_params", 1))
    if m.get("extra_where"):
        filtros.append(m["extra_where"])
    return ("WHERE " + " AND ".join(filtros)) if filtros else "", params


def _serie_mensual(cur, m, anio=None, nombre=None):
    """[(mes:date, valor:int, monto:int), ...] ascendente por mes."""
    where, params = _where_modulo(m, anio, nombre)
    cur.execute(
        f"""
        SELECT DATE_TRUNC('month', {m['fecha']})::date AS mes,
               {m['metrica']} AS valor,
               {m['monto']}   AS monto,
               MAX({m['fecha']}) AS ultima
        FROM {m['tabla']}
        {where}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )
    return [
        (f["mes"], int(f["valor"] or 0), int(f["monto"] or 0), f["ultima"])
        for f in cur.fetchall()
    ]


def _fmt_monto(m, valor):
    return miles(valor) if m.get("monto_formato") == "miles" else pesos(valor)


def _estado(rezago):
    if rezago <= UMBRAL_DIAS / 2:
        return "ok"
    if rezago <= UMBRAL_DIAS:
        return "warn"
    return "bad"


def get_panel(anio=None, mes=None, nombre=None, hoy=None):
    """Panel por módulo + alertas + tendencia.

    Devuelve un dict:
      - modulos: lista en el orden de MODULOS, cada uno con
          clave, titulo, url, url_carga, url_carga_args, unidad, nombre_desc,
          mes_ref, valor, valor_fmt, delta, monto_fmt, monto_label,
          ultima, ultima_fmt, dias_hoy, rezago, estado, sin_datos (bool)
      - lider: título del módulo más al día y su última jornada formateada
      - alertas: [{"nivel": "bad"|"warn"|"info", "texto": ...}]
      - tendencia: {labels, getnet, premios} últimos 6 meses (o None)
      - totales_mes: {"mes_ref", "ops", "delta"} Getnet + Premios del mes de referencia
    o None si ninguna tabla existe.
    """
    hoy = hoy or date.today()
    mes_filtro = int(mes) if mes else None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            series = {}
            for m in MODULOS:
                if _tabla_existe(cur, m["tabla"]):
                    series[m["clave"]] = _serie_mensual(cur, m, anio, nombre)
            jefaturas_sin_area = 0
            if _tabla_existe(cur, "jefaturas"):
                cur.execute(
                    "SELECT COUNT(*) AS n FROM jefaturas WHERE area IS NULL OR TRIM(area) = ''"
                )
                jefaturas_sin_area = int((cur.fetchone() or {}).get("n") or 0)
    finally:
        conn.close()

    if not series:
        return None

    modulos = []
    for m in MODULOS:
        serie = series.get(m["clave"])
        if serie is None:
            continue
        item = {
            "clave": m["clave"],
            "titulo": m["titulo"],
            "url": m["url"],
            "url_carga": m["url_carga"],
            "url_carga_args": m.get("url_carga_args", {}),
            "unidad": m["unidad"],
            "monto_label": m.get("monto_label", "Monto"),
            "nombre_desc": m["nombre_desc"],
            "sin_datos": not serie,
        }
        if serie:
            # Mes de referencia: el pedido por filtro (si existe en la serie) o
            # el último con datos. El anterior es el mes calendario previo.
            por_mes = {s[0]: s for s in serie}
            if mes_filtro:
                candidatos = [s for s in serie if s[0].month == mes_filtro]
                ref = candidatos[-1] if candidatos else None
            else:
                ref = serie[-1]
            if ref:
                mes_ref = ref[0]
                prev_key = (mes_ref.replace(month=mes_ref.month - 1) if mes_ref.month > 1
                            else mes_ref.replace(year=mes_ref.year - 1, month=12))
                prev = por_mes.get(prev_key)
                # Mes parcial: la última jornada del mes no llega a fin de mes
                # (p. ej. carga quincenal). El Δ contra un mes completo engaña.
                ultimo_dia = (mes_ref.replace(month=mes_ref.month % 12 + 1, day=1,
                                              year=mes_ref.year + (mes_ref.month == 12))
                              - timedelta(days=1))
                parcial = ref[3] < ultimo_dia
                item.update(
                    {
                        "mes_ref": mes_anio_es(mes_ref),
                        "valor": ref[1],
                        "valor_fmt": miles(ref[1]),
                        "delta": variacion(ref[1], prev[1]) if prev else None,
                        "monto_fmt": _fmt_monto(m, ref[2]),
                        "delta_monto": variacion(ref[2], prev[2]) if prev else None,
                        "parcial": parcial,
                        "parcial_hasta": fecha_corta(ref[3]) if parcial else None,
                    }
                )
            else:
                item["sin_datos"] = True
            ultima = max(s[3] for s in serie)
            item["ultima"] = ultima
            item["ultima_fmt"] = fecha_corta(ultima)
            item["dias_hoy"] = (hoy - ultima).days
        modulos.append(item)

    con_fecha = [i for i in modulos if i.get("ultima")]
    lider = max(con_fecha, key=lambda i: i["ultima"]) if con_fecha else None
    for i in modulos:
        if i.get("ultima") and lider:
            i["rezago"] = (lider["ultima"] - i["ultima"]).days
            i["estado"] = _estado(i["rezago"])
        else:
            i["rezago"] = None
            i["estado"] = "none"

    # --- Alertas ---
    alertas = []
    for i in modulos:
        if i["estado"] == "bad":
            alertas.append(
                {
                    "nivel": "bad",
                    "texto": (
                        f"{i['titulo']} está {i['rezago']} días por detrás "
                        f"(última jornada {i['ultima_fmt']}; el resto llega al {lider['ultima_fmt']})."
                    ),
                    "url": i["url_carga"],
                    "url_args": i["url_carga_args"],
                    "accion": "Cargar",
                }
            )
        elif i["estado"] == "warn":
            alertas.append(
                {
                    "nivel": "warn",
                    "texto": f"{i['titulo']} lleva {i['rezago']} días de rezago (última jornada {i['ultima_fmt']}).",
                    "url": i["url_carga"],
                    "url_args": i["url_carga_args"],
                    "accion": "Cargar",
                }
            )
        elif i["sin_datos"]:
            alertas.append(
                {
                    "nivel": "info",
                    "texto": f"{i['titulo']} no tiene datos para este filtro.",
                    "url": i["url_carga"],
                    "url_args": i["url_carga_args"],
                    "accion": "Cargar",
                }
            )
    if lider and lider["dias_hoy"] > 35:
        alertas.insert(
            0,
            {
                "nivel": "warn",
                "texto": (
                    f"Ningún módulo tiene datos de los últimos {lider['dias_hoy']} días "
                    f"(la jornada más reciente cargada es {lider['ultima_fmt']})."
                ),
                "url": "upload.upload",
                "url_args": {},
                "accion": "Cargar",
            },
        )
    if jefaturas_sin_area:
        alertas.append(
            {
                "nivel": "warn",
                "texto": (
                    f"{jefaturas_sin_area} jefatura(s) sin área asignada: sus cortesías "
                    f"no se atribuyen a MDA / MDJ / MRK en Análisis general."
                ),
                "url": "config.index",
                "url_args": {"seccion": "jefaturas"},
                "accion": "Revisar",
            }
        )

    # --- Tendencia 6 meses (Getnet + Premios) ---
    tendencia = None
    g = series.get("getnet") or []
    p = series.get("premios") or []
    meses_set = sorted({s[0] for s in g} | {s[0] for s in p})[-6:]
    if meses_set:
        gm = {s[0]: s[1] for s in g}
        pm = {s[0]: s[1] for s in p}
        tendencia = {
            "labels": [mes_anio_es(x) for x in meses_set],
            "getnet": [gm.get(x, 0) for x in meses_set],
            "premios": [pm.get(x, 0) for x in meses_set],
        }

    # --- Totales del mes de referencia (Getnet + Premios) ---
    totales_mes = None
    items = {i["clave"]: i for i in modulos}
    ig, ip = items.get("getnet"), items.get("premios")
    if ig and ip and not ig["sin_datos"] and not ip["sin_datos"] and ig.get("mes_ref") == ip.get("mes_ref"):
        gm = {s[0]: s[1] for s in g}
        pm = {s[0]: s[1] for s in p}
        ref = next((x for x in sorted(set(gm) | set(pm), reverse=True)
                    if mes_anio_es(x) == ig["mes_ref"]), None)
        if ref:
            prev_key = (ref.replace(month=ref.month - 1) if ref.month > 1
                        else ref.replace(year=ref.year - 1, month=12))
            actual = gm.get(ref, 0) + pm.get(ref, 0)
            hay_prev = prev_key in gm or prev_key in pm
            anterior = (gm.get(prev_key, 0) + pm.get(prev_key, 0)) if hay_prev else None
            totales_mes = {
                "mes_ref": ig["mes_ref"],
                "ops": miles(actual),
                "getnet": miles(gm.get(ref, 0)),
                "premios": miles(pm.get(ref, 0)),
                "delta": variacion(actual, anterior) if anterior else None,
            }

    return {
        "modulos": modulos,
        "lider": {"titulo": lider["titulo"], "ultima_fmt": lider["ultima_fmt"]} if lider else None,
        "alertas": alertas,
        "tendencia": tendencia,
        "totales_mes": totales_mes,
        "umbral": UMBRAL_DIAS,
    }


def get_estado_cargas():
    """Última carga registrada por módulo en `upload_log`.

    Devuelve una lista alineada con MODULOS (solo los que tienen log):
        [{"clave", "titulo", "archivo", "usuario", "fecha", "insertadas",
          "omitidas", "total"}, ...]
    o [] si la tabla no existe / está vacía.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if not _tabla_existe(cur, "upload_log"):
                return []
            cur.execute(
                """
                SELECT DISTINCT ON (tipo)
                       tipo, archivo, usuario, uploaded_at,
                       rows_total, rows_inserted, rows_skipped
                FROM upload_log
                ORDER BY tipo, uploaded_at DESC
                """
            )
            por_tipo = {r["tipo"]: r for r in cur.fetchall()}
    finally:
        conn.close()

    salida = []
    for m in MODULOS:
        r = por_tipo.get(m["upload_tipo"])
        if not r:
            continue
        salida.append(
            {
                "clave": m["clave"],
                "titulo": m["titulo"],
                "archivo": r["archivo"],
                "usuario": r["usuario"] or "—",
                "fecha": fecha_hora(r["uploaded_at"]),
                "total": miles(r["rows_total"]),
                "insertadas": miles(r["rows_inserted"]),
                "omitidas": miles(r["rows_skipped"]),
                "sin_nuevas": (r["rows_inserted"] or 0) == 0 and (r["rows_total"] or 0) > 0,
            }
        )
    return salida


def get_anios_disponibles():
    """Años con datos en cualquiera de los módulos, de más reciente a más antiguo."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            partes = [
                f"SELECT DISTINCT EXTRACT(YEAR FROM {m['fecha']})::int AS anio FROM {m['tabla']}"
                for m in MODULOS
                if _tabla_existe(cur, m["tabla"])
            ]
            if not partes:
                return []
            cur.execute(f"SELECT DISTINCT anio FROM ({' UNION '.join(partes)}) a ORDER BY 1 DESC")
            return [int(f["anio"]) for f in cur.fetchall()]
    finally:
        conn.close()
