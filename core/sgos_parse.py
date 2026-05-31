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
from datetime import date, datetime

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
