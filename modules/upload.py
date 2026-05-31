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
    construir_id_unico_premios,
    limpiar_id_cliente,
    limpiar_monto,
    limpiar_texto,
    normalizar_jornada,
    normalizar_maquina,
    normalizar_voucher,
    parsear_fecha,
)
from repositories import getnet_repository, premios_repository, upload_repository

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
