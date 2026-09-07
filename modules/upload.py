"""Carga de Excel Getnet: lee, limpia, valida e inserta en la tabla getnet."""
import pandas as pd
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core.auth import current_user, login_required
from core.sgos_parse import (
    calcular_jornada_premios,
    construir_id_unico,
    construir_id_unico_coinin,
    construir_id_unico_comps,
    construir_id_unico_mesas,
    construir_id_unico_premios,
    limpiar_consumo_id,
    limpiar_entero_opcional,
    limpiar_id_cliente,
    limpiar_id_sesion,
    limpiar_micros,
    limpiar_monto,
    limpiar_player_id,
    limpiar_puntos_obtenidos,
    limpiar_texto,
    limpiar_usuario_id,
    normalizar_fecha_operacion,
    normalizar_jornada,
    normalizar_maquina,
    normalizar_voucher,
    parsear_fecha,
)
from repositories import (
    coinin_repository,
    comps_repository,
    config_repository,
    getnet_repository,
    mesas_repository,
    premios_repository,
    upload_repository,
)

upload_bp = Blueprint("upload", __name__)

# Hoja y columnas que esperamos en el Excel Getnet.
SHEET = "Sheet1"
# Solo estas columnas son obligatorias (las que realmente usamos).
# "Validador" e "Ingreso CAWA" pueden venir o no; no las necesitamos.
COLUMNAS_REQUERIDAS = [
    "Jornada",
    "Fecha",
    "Id Cliente",
    "Monto",
    "Voucher",
    "Slot Attendant",
    "Forma Pago",
]

# Columnas obligatorias del Excel de Premios (las que realmente usamos).
# Otras columnas (Propina, Validador, Ingreso CAWA, etc.) pueden venir o no.
COLUMNAS_REQUERIDAS_PREMIOS = [
    "Fecha",
    "Máquina",
    "ID Mensaje",
    "Cliente",
    "Transferencia Final",
    "Slot Attendant",
    "Tipo de Pago",
]

# Hoja y encabezado del Excel de COMPS.
# La hoja tiene celdas combinadas en las primeras filas; el encabezado real
# está en la fila 8 -> header=7 (los datos empiezan en la fila 9).
SHEET_COMPS = "RrtIformeGeneral"
HEADER_COMPS = 7
# Columnas obligatorias del Excel de COMPS (las que realmente usamos).
# "Fecha Jornada" NO es obligatoria: la recalculamos desde "Fecha Real".
COLUMNAS_REQUERIDAS_COMPS = [
    "Consumo Id",
    "Fecha Real",
    "Cliente Id",
    "Nombre Cliente",
    "Descripcion Cat",
    "Descripcion Prod",
    "Micros",
    "Estado",
    "Usuario Id",
    "Nombre",
]

# Columnas del Excel de Coin In (MDA y MDJ comparten estructura).
# El reporte trae muchas más columnas; solo se guardan estas.
COLUMNAS_REQUERIDAS_COININ = [
    "Gaming Date",
    "Player ID",
    "Full Name",
    "Player Level",
    "Coin In Amount",
    "Prom Jugado",
    "Total Games played",
]
SISTEMAS_COININ = {"mda": "MDA"}

# Columnas obligatorias del Excel de Mesas ("Traking SGOS"), usado por Coin In MDJ.
# ID_SESION identifica la sesión (se usa como id_unico); el resto son los
# campos que se guardan en la tabla `mesas`.
COLUMNAS_REQUERIDAS_MESAS = [
    "ID_SESION",
    "ID_CLIENTE",
    "NOMBRE",
    "CATEGORIA",
    "MESA",
    "JUEGO",
    "FECHA_OPERACION",
    "PUNTOS_OBTENIDOS",
]


def _fila_vacia(fila):
    """True si toda la fila viene vacía (se ignora)."""
    return all(
        (valor is None) or (isinstance(valor, float) and pd.isna(valor))
        for valor in fila.values()
    )


def _normalizar_columnas(df):
    """Colapsa espacios y saltos de línea de los encabezados del Excel."""
    df.columns = [" ".join(str(col).split()) for col in df.columns]
    return df


def _valor_a_texto(valor):
    """Convierte una celda a texto sin pasar por float."""
    if valor is None:
        return ""
    if isinstance(valor, float):
        return str(int(valor)) if valor.is_integer() else str(valor)
    return str(valor).strip()


def _converters_texto(archivo, columnas, **opciones_lectura):
    """Arma el `converters` que obliga a leer ciertas columnas como texto.

    Los ID de tarjeta tienen 21 dígitos y NO caben en int64, así que pandas los
    infiere como float y terminan guardados en notación científica
    ('3.0172e+20'), perdiendo dígitos de forma irreversible. Con un converter,
    pandas entrega el valor tal cual lo lee openpyxl (int exacto) y solo lo
    pasamos a texto.

    Lee primero solo los encabezados para resolver el nombre real de cada
    columna (pueden traer saltos de línea) y deja el archivo rebobinado.
    """
    encabezados = pd.read_excel(archivo, nrows=0, **opciones_lectura).columns
    archivo.seek(0)
    buscadas = {c.lower() for c in columnas}
    return {
        col: _valor_a_texto
        for col in encabezados
        if " ".join(str(col).split()).lower() in buscadas
    }


def _resolver_columnas(df, requeridas):
    """Empareja las columnas requeridas sin distinguir mayúsculas.

    Devuelve (mapa, faltantes), donde mapa[requerida] es el nombre real de la
    columna en el DataFrame. Los reportes de Coin In cambian la capitalización
    entre exportaciones ("Total Games played" / "Total Games Played").
    """
    disponibles = {col.lower(): col for col in df.columns}
    mapa, faltantes = {}, []
    for requerida in requeridas:
        real = disponibles.get(requerida.lower())
        if real is None:
            faltantes.append(requerida)
        else:
            mapa[requerida] = real
    return mapa, faltantes


@upload_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("upload.html", user=current_user())

    # 1) Validar que llegó un archivo.
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Debe seleccionar un archivo Excel.", "error")
        return redirect(url_for("upload.upload"))

    # 2) Leer el Excel. El encabezado real está en la fila 2 -> header=1.
    #    "Id Cliente" se fuerza a texto: aunque hoy llega con comilla inicial,
    #    si el Excel alguna vez lo exporta como número se perderían dígitos
    #    (ver _converters_texto).
    try:
        opciones = {"sheet_name": SHEET, "header": 1}
        convert = _converters_texto(archivo, ["Id Cliente"], **opciones)
        df = pd.read_excel(archivo, converters=convert, **opciones)
    except Exception as exc:
        flash(f"No se pudo leer el Excel: {exc}", "error")
        return redirect(url_for("upload.upload"))

    # 3) Validar columnas requeridas; avisar exactamente cuál falta.
    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltantes:
        flash(
            "Faltan columnas requeridas en el Excel: " + ", ".join(faltantes),
            "error",
        )
        return redirect(url_for("upload.upload"))

    # 4) Recorrer filas, limpiar y transformar.
    filas = []
    procesados = 0
    errores = []
    for indice, registro in df.iterrows():
        fila = registro.to_dict()
        if _fila_vacia(fila):
            continue  # ignoramos filas completamente vacías

        # Número de fila en el Excel (header=1 -> datos desde la fila 3).
        fila_excel = indice + 3
        try:
            jornada = normalizar_jornada(fila["Jornada"])
            fecha = parsear_fecha(fila["Fecha"])
            id_cliente = limpiar_id_cliente(fila["Id Cliente"])
            monto = limpiar_monto(fila["Monto"])
            voucher = normalizar_voucher(fila["Voucher"])
            slot_attendant = limpiar_texto(fila["Slot Attendant"])
            forma_pago = limpiar_texto(fila["Forma Pago"])

            id_unico = construir_id_unico(jornada, fecha, id_cliente, monto, voucher)

            filas.append(
                {
                    "id_unico": id_unico,
                    "jornada": jornada,
                    "fecha": fecha,
                    "monto": monto,
                    "slot_attendant": slot_attendant,
                    "forma_pago": forma_pago,
                }
            )
            procesados += 1
        except Exception as exc:
            errores.append(f"Fila {fila_excel}: {exc}")

    # Si ninguna fila válida, avisamos.
    if not filas:
        detalle = " ".join(errores[:5]) if errores else ""
        flash(f"No se encontraron filas válidas para cargar. {detalle}", "error")
        return redirect(url_for("upload.upload"))

    # 5) Insertar evitando duplicados.
    try:
        resultado = getnet_repository.insertar_filas(filas)
    except Exception as exc:
        flash(f"Error al guardar en la base de datos: {exc}", "error")
        return redirect(url_for("upload.upload"))

    # 6) Registrar la carga en upload_log.
    usuario = (current_user() or {}).get("username") or "desconocido"
    try:
        upload_repository.registrar_carga(
            tipo="getnet",
            archivo=archivo.filename,
            usuario=usuario,
            rows_total=procesados,
            rows_inserted=resultado["inserted"],
            rows_skipped=resultado["skipped"],
        )
    except Exception:
        pass  # el registro de log no debe romper la carga

    # 7) Mostrar resumen al usuario.
    mensaje = (
        f"Carga completada: {procesados} procesados, "
        f"{resultado['inserted']} insertados, "
        f"{resultado['skipped']} duplicados."
    )
    if errores:
        mensaje += f" {len(errores)} fila(s) con error fueron omitidas."
    flash(mensaje, "success")
    return redirect(url_for("getnet.dashboard"))


@upload_bp.route("/upload/premios", methods=["GET", "POST"])
@login_required
def upload_premios():
    """Carga del Excel de Premios.

    El Excel tiene la hoja "Sheet1" con el encabezado real en la fila 2
    (header=1) y los datos desde la fila 3. Se valida, limpia, calcula la
    jornada (regla 10:00 AM -> 09:00 AM), se arma el id_unico y se inserta
    evitando duplicados.
    """
    if request.method == "GET":
        return render_template("upload_premios.html", user=current_user())

    # 1) Validar que llegó un archivo.
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Debe seleccionar un archivo Excel.", "error")
        return redirect(url_for("upload.upload_premios"))

    # 2) Leer el Excel. El encabezado real está en la fila 2 -> header=1.
    try:
        df = pd.read_excel(archivo, sheet_name=SHEET, header=1)
    except Exception as exc:
        flash(f"No se pudo leer el Excel: {exc}", "error")
        return redirect(url_for("upload.upload_premios"))

    # 3) Validar columnas requeridas; avisar exactamente cuál falta.
    faltantes = [c for c in COLUMNAS_REQUERIDAS_PREMIOS if c not in df.columns]
    if faltantes:
        flash(
            "Faltan columnas requeridas en el Excel: " + ", ".join(faltantes),
            "error",
        )
        return redirect(url_for("upload.upload_premios"))

    # 4) Recorrer filas, limpiar y transformar.
    filas = []
    procesados = 0
    errores = []
    for indice, registro in df.iterrows():
        fila = registro.to_dict()
        if _fila_vacia(fila):
            continue  # ignoramos filas completamente vacías

        # Número de fila en el Excel (header=1 -> datos desde la fila 3).
        fila_excel = indice + 3
        try:
            # La columna "Fecha" trae fecha + hora; la necesitamos para la jornada.
            fecha_hora = parsear_fecha(fila["Fecha"])
            jornada = calcular_jornada_premios(fecha_hora)
            maquina = normalizar_maquina(fila["Máquina"])
            cliente = limpiar_texto(fila["Cliente"])
            transferencia_final = limpiar_monto(fila["Transferencia Final"])
            slot_attendant = limpiar_texto(fila["Slot Attendant"])
            tipo_de_pago = limpiar_texto(fila["Tipo de Pago"])

            id_unico = construir_id_unico_premios(
                fila["ID Mensaje"],
                fecha_hora,
                jornada,
                maquina,
                cliente,
                transferencia_final,
                tipo_de_pago,
            )

            filas.append(
                {
                    "id_unico": id_unico,
                    # En la base, fecha es TIMESTAMP (guardamos la hora para los
                    # gráficos por hora); jornada se guarda como DATE.
                    "fecha": fecha_hora,
                    "jornada": jornada,
                    "maquina": maquina,
                    "cliente": cliente,
                    "transferencia_final": transferencia_final,
                    "slot_attendant": slot_attendant,
                    "tipo_de_pago": tipo_de_pago,
                }
            )
            procesados += 1
        except Exception as exc:
            errores.append(f"Fila {fila_excel}: {exc}")

    # Si ninguna fila válida, avisamos.
    if not filas:
        detalle = " ".join(errores[:5]) if errores else ""
        flash(f"No se encontraron filas válidas para cargar. {detalle}", "error")
        return redirect(url_for("upload.upload_premios"))

    # 5) Insertar evitando duplicados (crea la tabla si aún no existe).
    try:
        premios_repository.ensure_premios_schema()
        resultado = premios_repository.insertar_filas(filas)
    except Exception as exc:
        flash(f"Error al guardar en la base de datos: {exc}", "error")
        return redirect(url_for("upload.upload_premios"))

    # 6) Registrar la carga en upload_log.
    usuario = (current_user() or {}).get("username") or "desconocido"
    try:
        upload_repository.registrar_carga(
            tipo="premios",
            archivo=archivo.filename,
            usuario=usuario,
            rows_total=procesados,
            rows_inserted=resultado["inserted"],
            rows_skipped=resultado["skipped"],
        )
    except Exception:
        pass  # el registro de log no debe romper la carga

    # 7) Mostrar resumen al usuario.
    mensaje = (
        f"Carga completada: {procesados} procesados, "
        f"{resultado['inserted']} insertados, "
        f"{resultado['skipped']} duplicados."
    )
    if errores:
        mensaje += f" {len(errores)} fila(s) con error fueron omitidas."
    flash(mensaje, "success")
    return redirect(url_for("premios.dashboard"))


@upload_bp.route("/upload/comps", methods=["GET", "POST"])
@login_required
def upload_comps():
    """Carga del Excel de COMPS.

    El Excel tiene la hoja "RrtIformeGeneral" con celdas combinadas en las
    primeras filas; el encabezado real está en la fila 8 (header=7) y los datos
    desde la fila 9.

    Reglas:
      - Solo se guardan las filas cuyo Estado sea "QUEMADO" (las VALIDO u otros
        se cuentan pero no se insertan).
      - "Fecha Real" se guarda como TIMESTAMP (conserva la hora).
      - La jornada se RECALCULA desde la hora de "Fecha Real" con la regla
        10:00 AM -> 09:00 AM (misma que Premios) y se guarda como DATE.
      - El id_unico preferido es "Consumo Id".
      - Con el mismo Excel también se rellena la tabla `jefaturas`
        (Usuario Id + Nombre) para las jefaturas que aún no existan.
    """
    if request.method == "GET":
        return render_template("upload_comps.html", user=current_user())

    # 1) Validar que llegó un archivo.
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Debe seleccionar un archivo Excel.", "error")
        return redirect(url_for("upload.upload_comps"))

    # 2) Leer el Excel. El encabezado real está en la fila 8 -> header=7.
    #    "Cliente Id" se fuerza a texto: es un número de 21 dígitos que pandas
    #    convertiría a float y guardaría como '3.0172e+20' (ver _converters_texto).
    try:
        opciones = {"sheet_name": SHEET_COMPS, "header": HEADER_COMPS}
        convert = _converters_texto(archivo, ["Cliente Id"], **opciones)
        df = pd.read_excel(archivo, converters=convert, **opciones)
    except Exception as exc:
        flash(f"No se pudo leer el Excel: {exc}", "error")
        return redirect(url_for("upload.upload_comps"))

    # 2b) Normalizar los nombres de columna. En el Excel los encabezados pueden
    # traer saltos de línea o espacios dobles (ej. "Fecha\nReal"), por lo que
    # colapsamos cualquier espacio en blanco a un solo espacio y quitamos los
    # de los extremos. Así "Fecha Real" coincide aunque venga con salto de línea.
    df.columns = [" ".join(str(col).split()) for col in df.columns]

    # 3) Validar columnas requeridas; avisar exactamente cuál falta.
    faltantes = [c for c in COLUMNAS_REQUERIDAS_COMPS if c not in df.columns]
    if faltantes:
        flash(
            "Faltan columnas requeridas en el Excel: " + ", ".join(faltantes),
            "error",
        )
        return redirect(url_for("upload.upload_comps"))

    # 4) Recorrer filas, filtrar QUEMADO, limpiar y transformar.
    filas = []
    pares_jefaturas = []  # (usuario_id, nombre) para rellenar jefaturas
    leidos = 0            # filas no vacías leídas
    quemados = 0          # filas QUEMADO (las que sí procesamos)
    errores = []
    for indice, registro in df.iterrows():
        fila = registro.to_dict()
        if _fila_vacia(fila):
            continue  # ignoramos filas completamente vacías
        leidos += 1

        # Número de fila en el Excel (header=7 -> datos desde la fila 9).
        fila_excel = indice + 9

        # Filtro de negocio: solo nos interesan los consumos "QUEMADO".
        estado = limpiar_texto(fila["Estado"])
        if estado.strip().upper() != "QUEMADO":
            continue
        quemados += 1

        try:
            # "Fecha Real" trae fecha + hora; la necesitamos para la jornada.
            fecha_real = parsear_fecha(fila["Fecha Real"])
            fecha_jornada = calcular_jornada_premios(fecha_real)
            cliente_id = limpiar_id_cliente(fila["Cliente Id"])
            nombre_cliente = limpiar_texto(fila["Nombre Cliente"])
            descripcion_cat = limpiar_texto(fila["Descripcion Cat"])
            descripcion_prod = limpiar_texto(fila["Descripcion Prod"])
            micros = limpiar_micros(fila["Micros"])
            usuario_id = limpiar_usuario_id(fila["Usuario Id"])
            nombre = limpiar_texto(fila["Nombre"])

            id_unico = construir_id_unico_comps(
                fila["Consumo Id"],
                fecha_real,
                cliente_id,
                descripcion_prod,
                micros,
                usuario_id,
            )

            filas.append(
                {
                    "id_unico": id_unico,
                    "fecha_real": fecha_real,      # TIMESTAMP (con hora)
                    "fecha_jornada": fecha_jornada,  # DATE (recalculada)
                    "cliente_id": cliente_id,
                    "nombre_cliente": nombre_cliente,
                    "descripcion_cat": descripcion_cat,
                    "descripcion_prod": descripcion_prod,
                    "micros": micros,
                    "estado": estado,
                    "usuario_id": usuario_id,
                    "nombre": nombre,
                }
            )
            # Guardamos el par para rellenar jefaturas (si hay usuario_id).
            if usuario_id:
                pares_jefaturas.append((usuario_id, nombre))
        except Exception as exc:
            errores.append(f"Fila {fila_excel}: {exc}")

    # Si ninguna fila QUEMADO válida, avisamos.
    if not filas:
        if quemados == 0:
            flash(
                f"No se encontraron filas con Estado 'QUEMADO' "
                f"({leidos} fila(s) leídas).",
                "error",
            )
        else:
            detalle = " ".join(errores[:5]) if errores else ""
            flash(f"No se encontraron filas válidas para cargar. {detalle}", "error")
        return redirect(url_for("upload.upload_comps"))

    # 5) Insertar evitando duplicados (crea la tabla si aún no existe).
    try:
        comps_repository.ensure_comps_schema()
        resultado = comps_repository.insertar_filas(filas)
    except Exception as exc:
        flash(f"Error al guardar en la base de datos: {exc}", "error")
        return redirect(url_for("upload.upload_comps"))

    # 6) Rellenar jefaturas faltantes con el mismo Excel (no debe romper la carga).
    jefaturas_nuevas = 0
    try:
        jefaturas_nuevas = config_repository.upsert_jefaturas_desde_comps(
            pares_jefaturas
        )
    except Exception:
        pass

    # 7) Registrar la carga en upload_log.
    usuario = (current_user() or {}).get("username") or "desconocido"
    try:
        upload_repository.registrar_carga(
            tipo="comps",
            archivo=archivo.filename,
            usuario=usuario,
            rows_total=quemados,
            rows_inserted=resultado["inserted"],
            rows_skipped=resultado["skipped"],
        )
    except Exception:
        pass  # el registro de log no debe romper la carga

    # 8) Mostrar resumen al usuario.
    mensaje = (
        f"Carga completada: {leidos} leídos, {quemados} QUEMADO, "
        f"{resultado['inserted']} insertados, "
        f"{resultado['skipped']} duplicados."
    )
    if jefaturas_nuevas:
        mensaje += f" {jefaturas_nuevas} jefatura(s) nueva(s) agregada(s)."
    if errores:
        mensaje += f" {len(errores)} fila(s) con error fueron omitidas."
    flash(mensaje, "success")
    return redirect(url_for("comps.dashboard"))


@upload_bp.route("/upload/coinin/<sistema>", methods=["GET", "POST"])
@login_required
def upload_coinin(sistema):
    """Carga del Excel de Coin In (MDA o MDJ).

    Ambos reportes comparten estructura y se guardan en la misma tabla,
    distinguidos por la columna `sistema`.

    El archivo trae filas de título antes del encabezado real, así que la fila
    de encabezado se detecta buscando "Gaming Date" en vez de fijarla.

    Reglas:
      - "Gaming Date" es directamente la jornada (el reporte ya viene agregado
        por jugador y día, no hay que recalcularla).
      - Los montos pueden venir con formato "$1.652.845"; una celda vacía se
        interpreta como 0 (sin actividad).
      - id_unico = sistema + jornada + Player ID.
    """
    clave = (sistema or "").lower()
    if clave not in SISTEMAS_COININ:
        flash("Sistema de Coin In desconocido.", "error")
        return redirect(url_for("coinin.index"))
    nombre_sistema = SISTEMAS_COININ[clave]

    if request.method == "GET":
        return render_template(
            "upload_coinin.html", user=current_user(), sistema=nombre_sistema
        )

    # 1) Validar que llegó un archivo.
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Debe seleccionar un archivo Excel.", "error")
        return redirect(url_for("upload.upload_coinin", sistema=clave))

    # 2) Localizar la fila de encabezado y leer el Excel desde ahí.
    try:
        previo = pd.read_excel(archivo, sheet_name=0, header=None, nrows=30)
        fila_encabezado = None
        for indice, valores in previo.iterrows():
            textos = [" ".join(str(v).split()).lower() for v in valores.tolist()]
            if "gaming date" in textos:
                fila_encabezado = indice
                break
        if fila_encabezado is None:
            flash(
                "No se encontró la fila de encabezado ('Gaming Date') en el Excel.",
                "error",
            )
            return redirect(url_for("upload.upload_coinin", sistema=clave))

        archivo.seek(0)
        opciones = {"sheet_name": 0, "header": fila_encabezado}
        convert = _converters_texto(archivo, ["Player ID"], **opciones)
        df = _normalizar_columnas(
            pd.read_excel(archivo, converters=convert, **opciones)
        )
    except Exception as exc:
        flash(f"No se pudo leer el Excel: {exc}", "error")
        return redirect(url_for("upload.upload_coinin", sistema=clave))

    # 3) Validar columnas requeridas; avisar exactamente cuál falta.
    cols, faltantes = _resolver_columnas(df, COLUMNAS_REQUERIDAS_COININ)
    if faltantes:
        flash(
            "Faltan columnas requeridas en el Excel: " + ", ".join(faltantes),
            "error",
        )
        return redirect(url_for("upload.upload_coinin", sistema=clave))

    # 4) Recorrer filas, limpiar y transformar.
    filas = []
    procesados = 0
    errores = []
    for indice, registro in df.iterrows():
        fila = registro.to_dict()
        if _fila_vacia(fila):
            continue

        fila_excel = indice + fila_encabezado + 2
        try:
            player_id = limpiar_player_id(fila[cols["Player ID"]])
            if not player_id:
                continue  # filas de subtotal del reporte no traen jugador

            jornada = parsear_fecha(fila[cols["Gaming Date"]]).date()
            full_name = limpiar_texto(fila[cols["Full Name"]])
            player_level = limpiar_texto(fila[cols["Player Level"]])
            coin_in = limpiar_entero_opcional(fila[cols["Coin In Amount"]])
            prom_jugado = limpiar_entero_opcional(fila[cols["Prom Jugado"]])
            total_games = limpiar_entero_opcional(fila[cols["Total Games played"]])

            filas.append(
                {
                    "id_unico": construir_id_unico_coinin(
                        nombre_sistema, jornada, player_id
                    ),
                    "sistema": nombre_sistema,
                    "jornada": jornada,
                    "player_id": player_id,
                    "full_name": full_name,
                    "player_level": player_level,
                    "coin_in": coin_in,
                    "prom_jugado": prom_jugado,
                    "total_games": total_games,
                }
            )
            procesados += 1
        except Exception as exc:
            errores.append(f"Fila {fila_excel}: {exc}")

    if not filas:
        detalle = " ".join(errores[:5]) if errores else ""
        flash(f"No se encontraron filas válidas para cargar. {detalle}", "error")
        return redirect(url_for("upload.upload_coinin", sistema=clave))

    # 5) Insertar evitando duplicados (crea la tabla si aún no existe).
    try:
        coinin_repository.ensure_coinin_schema()
        resultado = coinin_repository.insertar_filas(filas)
    except Exception as exc:
        flash(f"Error al guardar en la base de datos: {exc}", "error")
        return redirect(url_for("upload.upload_coinin", sistema=clave))

    # 6) Registrar la carga en upload_log.
    usuario = (current_user() or {}).get("username") or "desconocido"
    try:
        upload_repository.registrar_carga(
            tipo=f"coinin_{clave}",
            archivo=archivo.filename,
            usuario=usuario,
            rows_total=procesados,
            rows_inserted=resultado["inserted"],
            rows_skipped=resultado["skipped"],
        )
    except Exception:
        pass  # el registro de log no debe romper la carga

    # 7) Mostrar resumen al usuario.
    mensaje = (
        f"Carga completada: {procesados} procesados, "
        f"{resultado['inserted']} insertados, "
        f"{resultado['skipped']} duplicados."
    )
    if errores:
        mensaje += f" {len(errores)} fila(s) con error fueron omitidas."
    flash(mensaje, "success")
    endpoint = "coinin.mda_dashboard" if clave == "mda" else "coinin.mdj_dashboard"
    return redirect(url_for(endpoint))


@upload_bp.route("/upload/mesas", methods=["GET", "POST"])
@login_required
def upload_mesas():
    """Carga del Excel de Mesas ("Traking SGOS"), usado por la pestaña Coin In MDJ.

    A diferencia de Coin In MDA, este reporte trae una fila POR SESIÓN (no
    viene agregado por jugador y día). Reglas:
      - FECHA_OPERACION es la jornada del registro (solo fecha, sin hora).
      - PUNTOS_OBTENIDOS se guarda tal cual y además como `coin_in`
        (PUNTOS_OBTENIDOS * 1000): el "seudo Coin In" equivalente a MDA/MDJ.
      - id_unico = ID_SESION (único por sesión); si viniera vacío, se arma
        con fecha + cliente + mesa + juego + puntos.
    """
    if request.method == "GET":
        return render_template("upload_mesas.html", user=current_user())

    # 1) Validar que llegó un archivo.
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        flash("Debe seleccionar un archivo Excel.", "error")
        return redirect(url_for("upload.upload_mesas"))

    # 2) Leer el Excel. "ID_CLIENTE" se fuerza a texto (mismo motivo que
    #    "Id Cliente"/"Player ID": son IDs de 21 dígitos que no caben en float64).
    try:
        opciones = {"sheet_name": 0, "header": 0}
        convert = _converters_texto(archivo, ["ID_CLIENTE"], **opciones)
        df = _normalizar_columnas(pd.read_excel(archivo, converters=convert, **opciones))
    except Exception as exc:
        flash(f"No se pudo leer el Excel: {exc}", "error")
        return redirect(url_for("upload.upload_mesas"))

    # 3) Validar columnas requeridas; avisar exactamente cuál falta.
    cols, faltantes = _resolver_columnas(df, COLUMNAS_REQUERIDAS_MESAS)
    if faltantes:
        flash(
            "Faltan columnas requeridas en el Excel: " + ", ".join(faltantes),
            "error",
        )
        return redirect(url_for("upload.upload_mesas"))

    # 4) Recorrer filas, limpiar y transformar.
    filas = []
    procesados = 0
    errores = []
    for indice, registro in df.iterrows():
        fila = registro.to_dict()
        if _fila_vacia(fila):
            continue  # ignoramos filas completamente vacías

        # Número de fila en el Excel (header=0 -> datos desde la fila 2).
        fila_excel = indice + 2
        try:
            id_sesion = limpiar_id_sesion(fila[cols["ID_SESION"]])
            id_cliente = limpiar_id_cliente(fila[cols["ID_CLIENTE"]])
            nombre = limpiar_texto(fila[cols["NOMBRE"]])
            categoria = limpiar_texto(fila[cols["CATEGORIA"]])
            mesa = limpiar_texto(fila[cols["MESA"]])
            juego = limpiar_texto(fila[cols["JUEGO"]])
            fecha_operacion = normalizar_fecha_operacion(fila[cols["FECHA_OPERACION"]])
            puntos = limpiar_puntos_obtenidos(fila[cols["PUNTOS_OBTENIDOS"]])

            filas.append(
                {
                    "id_unico": construir_id_unico_mesas(
                        id_sesion, fecha_operacion, id_cliente, mesa, juego, puntos
                    ),
                    "id_sesion": id_sesion,
                    "id_cliente": id_cliente,
                    "nombre": nombre,
                    "categoria": categoria,
                    "mesa": mesa,
                    "juego": juego,
                    "fecha_operacion": fecha_operacion,
                    "puntos_obtenidos": puntos,
                    "coin_in": puntos * 1000,
                }
            )
            procesados += 1
        except Exception as exc:
            errores.append(f"Fila {fila_excel}: {exc}")

    # Si ninguna fila válida, avisamos.
    if not filas:
        detalle = " ".join(errores[:5]) if errores else ""
        flash(f"No se encontraron filas válidas para cargar. {detalle}", "error")
        return redirect(url_for("upload.upload_mesas"))

    # 5) Insertar evitando duplicados (crea la tabla si aún no existe).
    try:
        mesas_repository.ensure_mesas_schema()
        resultado = mesas_repository.insertar_filas(filas)
    except Exception as exc:
        flash(f"Error al guardar en la base de datos: {exc}", "error")
        return redirect(url_for("upload.upload_mesas"))

    # 6) Registrar la carga en upload_log.
    usuario = (current_user() or {}).get("username") or "desconocido"
    try:
        upload_repository.registrar_carga(
            tipo="mesas",
            archivo=archivo.filename,
            usuario=usuario,
            rows_total=procesados,
            rows_inserted=resultado["inserted"],
            rows_skipped=resultado["skipped"],
        )
    except Exception:
        pass  # el registro de log no debe romper la carga

    # 7) Mostrar resumen al usuario (con ejemplos de error para poder
    #    diagnosticar sin tener que revisar logs del servidor).
    mensaje = (
        f"Carga completada: {procesados} procesados, "
        f"{resultado['inserted']} insertados, "
        f"{resultado['skipped']} duplicados."
    )
    if errores:
        mensaje += f" {len(errores)} fila(s) con error fueron omitidas."
        mensaje += " Ejemplos: " + " | ".join(errores[:5])
    flash(mensaje, "success")
    return redirect(url_for("coinin.mdj_dashboard"))
