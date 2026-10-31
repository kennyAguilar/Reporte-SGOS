"""Formateo de valores para la UI (montos, fechas).

- Montos en formato chileno: separador de miles con punto, sin decimales.
- Fecha larga en español: "31 de mayo de 2025".
- Mes cargado en inglés (como en el diseño): "May 2025".
- Fecha/hora de carga: "21/05/2026 22:51".
"""

MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

MESES_EN = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}


def miles(n):
    """Entero con separador de miles en punto: 112182200 -> '112.182.200'."""
    if n is None:
        n = 0
    return f"{int(round(float(n))):,}".replace(",", ".")


def pesos(n):
    """Monto en pesos: '$112.182.200'."""
    return "$" + miles(n)


def fecha_larga(d):
    """Fecha larga en español: '31 de mayo de 2025'."""
    if not d:
        return ""
    return f"{d.day} de {MESES_ES[d.month]} de {d.year}"


def mes_ingles(d):
    """Mes y año en inglés: 'May 2025'."""
    if not d:
        return ""
    return f"{MESES_EN[d.month]} {d.year}"


def mes_anio_es(d):
    """Mes y año en español, capitalizado: 'Abril 2025' (para ejes de gráficos)."""
    if not d:
        return ""
    return f"{MESES_ES[d.month].capitalize()} {d.year}"


def fecha_corta(d):
    """Fecha corta numérica: '01/01/2026' (día/mes/año)."""
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def fecha_hora(dt):
    """Fecha y hora de carga: '21/05/2026 22:51'."""
    if not dt:
        return ""
    return dt.strftime("%d/%m/%Y %H:%M")


def porcentaje(valor, total, decimales=1):
    """Porcentaje con coma decimal: porcentaje(25, 200) -> '12,5%'."""
    if not total:
        return "0%"
    pct = float(valor or 0) * 100 / float(total)
    return f"{pct:.{decimales}f}%".replace(".", ",")


def variacion(actual, anterior):
    """Variación porcentual entre dos valores, lista para mostrar en la UI.

    Devuelve un dict {"pct": "+12,3%", "dir": "up" | "down" | "flat"} o None si
    no hay base de comparación (anterior nulo o cero).
    """
    if actual is None or not anterior:
        return None
    pct = (float(actual) - float(anterior)) * 100 / float(anterior)
    if abs(pct) < 0.05:
        direccion = "flat"
    elif pct > 0:
        direccion = "up"
    else:
        direccion = "down"
    return {"pct": f"{pct:+.1f}%".replace(".", ","), "dir": direccion}
