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
    construir_id_unico_comps,
    construir_id_unico_premios,
    limpiar_consumo_id,
    limpiar_id_cliente,
    limpiar_micros,
    limpiar_monto,
    limpiar_texto,
    limpiar_usuario_id,
    normalizar_jornada,
    normalizar_maquina,
    normalizar_voucher,
    parsear_fecha,
)
from repositories import (
    comps_repository,
    config_repository,
    getnet_repository,
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


def _fila_vacia(fila):
    """True si toda la fila viene vacía (se ignora)."""
    return all(
        (valor is None) or (isinstance(valor, float) and pd.isna(valor))
        for valor in fila.values()
    )


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
    try:
        df = pd.read_excel(archivo, sheet_name=SHEET, header=1)
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
    return redirect(url_for("home.index"))


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
    try:
        df = pd.read_excel(archivo, sheet_name=SHEET_COMPS, header=HEADER_COMPS)
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

    # 8) Mostrar resumen al usuario (se queda en la página de carga).
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
    return redirect(url_for("upload.upload_comps"))
