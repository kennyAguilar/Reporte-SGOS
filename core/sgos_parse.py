"""Helpers para limpiar y transformar las filas del Excel Getnet.

La idea de este módulo es separar TODA la lógica de "limpieza de datos" del
resto de la aplicación. Así el blueprint de carga (modules/upload.py) queda
simple y estas funciones se pueden probar una por una.

Reglas de negocio (acordadas con el usuario):
- La jornada se toma de la columna "Jornada" del Excel (ya viene lista).
- La fecha (con hora) se guarda como TIMESTAMP para análisis por hora.
- El id_unico evita duplicados y debe ser ESTABLE: si se sube el mismo Excel
  otra vez, debe generar exactamente el mismo id_unico.
"""
from datetime import date, datetime, timedelta

import pandas as pd


def _es_vacio(valor):
    """True si el valor es None o NaN (celda vacía de pandas)."""
    return valor is None or (isinstance(valor, float) and pd.isna(valor))


def limpiar_texto(valor):
    """Convierte cualquier valor a texto sin espacios sobrantes.

    Una celda vacía se devuelve como cadena vacía ("").
    """
    if _es_vacio(valor):
        return ""
    return str(valor).strip()


def limpiar_id_cliente(valor):
    """Limpia el Id Cliente.

    En el Excel viene con una comilla simple inicial (ej: '301720020100077042767)
    porque Excel la usa para forzar que el número se trate como texto.
    Quitamos esa comilla inicial y los espacios.
    """
    texto = limpiar_texto(valor)
    if texto.startswith("'"):
        texto = texto[1:]
    return texto.strip()


def limpiar_monto(valor):
    """Convierte el Monto a entero.

    En este Excel el Monto ya viene como número entero (ej: 20000), pero
    limpiamos de forma defensiva por si en otro archivo llega como texto con
    símbolo "$" o puntos de miles (ej: "$20.000").
    """
    if _es_vacio(valor):
        raise ValueError("Monto vacío")

    # Si ya es un número, lo pasamos directo a entero.
    if isinstance(valor, (int, float)):
        return int(round(float(valor)))

    # Si es texto, quitamos todo lo que no sea dígito o signo menos.
    texto = str(valor).strip()
    limpio = "".join(c for c in texto if c.isdigit() or c == "-")
    if not limpio or limpio == "-":
        raise ValueError(f"Monto inválido: {valor!r}")
    return int(limpio)


def normalizar_voucher(valor):
    """Devuelve el Voucher como texto estable.

    Llega como número entero (ej: 973). Lo pasamos a texto sin la parte
    decimal que a veces agrega pandas (973.0 -> "973").
    """
    if _es_vacio(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    return str(valor).strip()


def normalizar_jornada(valor):
    """Convierte la columna Jornada a un objeto date (para guardar como DATE).

    Acepta date/datetime de pandas o texto ISO (2026-01-01).
    """
    if _es_vacio(valor):
        raise ValueError("Jornada vacía")
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    # Texto: dejamos que pandas lo interprete (la jornada viene en formato ISO).
    convertido = pd.to_datetime(valor, errors="coerce")
    if pd.isna(convertido):
        raise ValueError(f"Jornada inválida: {valor!r}")
    return convertido.date()


def parsear_fecha(valor):
    """Convierte la columna Fecha (con hora) a datetime para guardar TIMESTAMP.

    El formato del Excel es día-mes-año hora:minuto (ej: 01-01-2026 18:19),
    por eso usamos dayfirst=True.
    """
    if _es_vacio(valor):
        raise ValueError("Fecha vacía")
    if isinstance(valor, datetime):
        return valor
    convertido = pd.to_datetime(valor, dayfirst=True, errors="coerce")
    if pd.isna(convertido):
        raise ValueError(f"Fecha inválida: {valor!r}")
    return convertido.to_pydatetime()


def construir_id_unico(jornada, fecha, id_cliente, monto, voucher):
    """Crea un identificador único y estable para evitar duplicados.

    Incluimos la HORA (columna Fecha) porque el voucher se repite entre las
    distintas máquinas Getnet: dos operaciones reales pueden tener el mismo
    jornada + id_cliente + monto + voucher y solo se distinguen por la hora.

    Combinación: jornada (YYYY-MM-DD) + fecha-hora (ISO) + Id Cliente + Monto + Voucher.
    Ejemplo: 2026-01-01_2026-01-01T18:19:00_301720020100077042767_20000_973

    Es estable: al subir el mismo Excel otra vez, la misma fila genera el mismo
    id_unico (la hora no cambia), por lo que se detecta como duplicado.
    """
    jornada_iso = jornada.isoformat()          # date  -> "2026-01-01"
    fecha_iso = fecha.strftime("%Y-%m-%dT%H:%M:%S")  # datetime -> "2026-01-01T18:19:00"
    return f"{jornada_iso}_{fecha_iso}_{id_cliente}_{monto}_{voucher}"


# ---------------------------------------------------------------------------
# Helpers específicos del Excel de Premios
# ---------------------------------------------------------------------------
# El Excel de Premios es distinto al de Getnet:
#   - La columna "Fecha" trae fecha Y hora reales del registro.
#   - NO trae una columna "Jornada" lista: hay que CALCULARLA desde la hora.
#   - El identificador único preferido es la columna "ID Mensaje".


def normalizar_maquina(valor):
    """Devuelve la Máquina como texto limpio (sin perder datos).

    Puede llegar como número (ej: 12.0) o como texto. La dejamos como texto
    sin la parte decimal que a veces agrega pandas (12.0 -> "12"). Una celda
    vacía se devuelve como cadena vacía.
    """
    if _es_vacio(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    return str(valor).strip()


def limpiar_id_mensaje(valor):
    """Limpia el "ID Mensaje" para usarlo como id_unico.

    - Lo convertimos a texto.
    - Quitamos espacios sobrantes.
    - Quitamos la comilla simple inicial que Excel agrega para forzar texto
      (ej: '123456 -> 123456).

    Si viene vacío, devolvemos "" (el llamador decidirá la clave alternativa).
    """
    texto = limpiar_texto(valor)
    if texto.startswith("'"):
        texto = texto[1:]
    return texto.strip()


def calcular_jornada_premios(fecha):
    """Calcula la jornada operativa a partir de la Fecha (con hora) del registro.

    Regla de negocio: la jornada va de las 10:00 AM a las 09:00 AM del día
    siguiente.
      - Hora entre 10:00 y 23:59 -> la jornada es el MISMO día de la fecha.
      - Hora entre 00:00 y 09:59 -> la jornada es el día ANTERIOR.

    Ejemplos:
      01/01/2026 10:30 -> 01/01/2026
      01/01/2026 23:45 -> 01/01/2026
      02/01/2026 00:30 -> 01/01/2026
      02/01/2026 09:00 -> 01/01/2026
      02/01/2026 10:00 -> 02/01/2026

    Devuelve un objeto date (para guardar como DATE en la base).
    """
    if not isinstance(fecha, datetime):
        raise ValueError("La fecha para calcular la jornada debe incluir la hora")
    if fecha.hour >= 10:
        return fecha.date()
    # 00:00 a 09:59 -> pertenece a la jornada del día anterior.
    return (fecha - timedelta(days=1)).date()


def construir_id_unico_premios(
    id_mensaje, fecha, jornada, maquina, cliente, transferencia_final, tipo_de_pago
):
    """Crea un id_unico ESTABLE para evitar registros de Premios duplicados.

    Preferimos la columna "ID Mensaje" (ya limpia), que identifica el registro.
    Si "ID Mensaje" viene vacío, construimos una clave combinando los datos del
    registro. Normalizamos las fechas a formato ISO (YYYY-MM-DD) para que el
    id_unico no cambie por diferencias de formato visual.

    Es estable: al subir el mismo Excel otra vez, la misma fila genera el mismo
    id_unico y se detecta como duplicado.
    """
    base = limpiar_id_mensaje(id_mensaje)
    if base:
        return base

    # Fallback: combinación normalizada de los campos del registro.
    fecha_iso = (fecha.date() if isinstance(fecha, datetime) else fecha).isoformat()
    jornada_iso = jornada.isoformat()
    return (
        f"{fecha_iso}_{jornada_iso}_{maquina}_{cliente}_"
        f"{transferencia_final}_{tipo_de_pago}"
    )


# ---------------------------------------------------------------------------
# Helpers específicos del Excel de COMPS
# ---------------------------------------------------------------------------
# El Excel de COMPS (hoja "RrtIformeGeneral") trae:
#   - "Fecha Real" con fecha Y hora reales del consumo (se guarda TIMESTAMP).
#   - NO trae una jornada confiable: se RECALCULA desde la hora con la misma
#     regla que Premios (10:00 AM a 09:00 AM) -> reutilizamos
#     calcular_jornada_premios.
#   - El identificador único preferido es "Consumo Id".


def limpiar_consumo_id(valor):
    """Limpia el "Consumo Id" para usarlo como base del id_unico.

    - Lo convierte a texto y quita espacios.
    - Quita la comilla simple inicial que Excel agrega para forzar texto.
    - Quita la parte decimal innecesaria que a veces agrega pandas
      (229810.0 -> "229810").

    Si viene vacío, devuelve "" (el llamador usará la clave alternativa).
    """
    if _es_vacio(valor):
        return ""
    # Si es un número entero "disfrazado" de float, quitamos el .0.
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    texto = str(valor).strip()
    if texto.startswith("'"):
        texto = texto[1:]
    texto = texto.strip()
    # Caso "229810.0" llegado como texto: quitamos el .0 final.
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto


def limpiar_usuario_id(valor):
    """Devuelve el "Usuario Id" como texto sin espacios.

    Puede llegar como número (ej: 45.0) o texto. Lo dejamos como texto sin la
    parte decimal (45.0 -> "45") y sin espacios internos. Una celda vacía
    devuelve cadena vacía.
    """
    if _es_vacio(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, int):
        return str(valor)
    texto = str(valor).strip()
    if texto.startswith("'"):
        texto = texto[1:]
    # Sin espacios (ni internos): "12 34" -> "1234".
    return "".join(texto.split())


def limpiar_micros(valor):
    """Convierte la columna "Micros" a entero.

    Acepta número (45.0 -> 45) o texto con puntos de miles. Lanza ValueError
    si está vacío o no se puede convertir, para reportarlo por fila.
    """
    if _es_vacio(valor):
        raise ValueError("Micros vacío")
    if isinstance(valor, (int, float)):
        return int(round(float(valor)))
    texto = str(valor).strip()
    limpio = "".join(c for c in texto if c.isdigit() or c == "-")
    if not limpio or limpio == "-":
        raise ValueError(f"Micros inválido: {valor!r}")
    return int(limpio)


def construir_id_unico_comps(
    consumo_id, fecha_real, cliente_id, descripcion_prod, micros, usuario_id
):
    """Crea un id_unico ESTABLE para evitar comps duplicados.

    Preferimos "Consumo Id" (ya limpio). Si viene vacío, construimos una clave
    combinando los datos del registro, normalizando la fecha a ISO para que el
    id_unico no cambie por diferencias de formato visual.

    Es estable: al subir el mismo Excel otra vez, la misma fila genera el mismo
    id_unico y se detecta como duplicado.
    """
    base = limpiar_consumo_id(consumo_id)
    if base:
        return base

    # Fallback: fecha_real normalizada + datos identificadores del registro.
    fecha_iso = (
        fecha_real.strftime("%Y-%m-%dT%H:%M:%S")
        if isinstance(fecha_real, datetime)
        else str(fecha_real)
    )
    return f"{fecha_iso}_{cliente_id}_{descripcion_prod}_{micros}_{usuario_id}"
