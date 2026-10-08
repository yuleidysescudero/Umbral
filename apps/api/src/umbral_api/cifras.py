"""Cifras con formato periodístico y un único redondeo del puntaje (QA TVN 3.1 y 3.2).

- El puntaje se redondea UNA vez, aquí, con ROUND_HALF_UP sobre su representación decimal (74,55 → 74,6), y la API
  lo expone ya formateado (`scoreDisplay`): el texto «Por qué», la tarjeta y la exportación muestran el mismo número.
- Los valores de indicadores se muestran con coma decimal, miles con punto, porcentajes a 1 decimal y población en
  millones. La cita (`passage`) conserva el valor original exacto; solo cambia el texto mostrado.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: float, digits: int = 1) -> Decimal:
    """Redondeo comercial sobre el decimal que se ve (str), no sobre el binario del float (74.55 → 74.6, no 74.5)."""
    q = Decimal(1).scaleb(-digits)
    return Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)


def _es(d: Decimal, digits: int) -> str:
    """Decimal → texto con coma decimal y punto de miles (sin notación científica)."""
    sign = "-" if d < 0 else ""
    d = abs(d)
    text = f"{d:.{digits}f}"
    whole, _, frac = text.partition(".")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    out = ".".join(groups)
    return sign + out + ("," + frac if frac else "")


def score_display(value: float) -> str:
    """Puntaje 0–100 con un decimal y coma: 74,6."""
    return _es(round_half_up(value, 1), 1)


def fmt_es(value: float, digits: int = 2) -> str:
    """Número genérico: hasta `digits` decimales, sin ceros sobrantes ni notación científica."""
    d = round_half_up(value, digits)
    text = _es(d, digits)
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def format_value_es(value: float | None, unit: str | None = None) -> str:
    """Valor de un indicador listo para leer al aire: «1,5 % anual», «4,46 millones de personas», «12.345»."""
    if value is None:
        return "valor ausente en la fuente"
    u = (unit or "").strip()
    if u.startswith("%"):
        rest = u[1:].strip()
        return f"{_es(round_half_up(value, 1), 1)} %" + (f" {rest}" if rest else "")
    if u.lower() in {"personas", "people", "habitantes"}:
        if abs(value) >= 1_000_000:
            return f"{_es(round_half_up(value / 1_000_000, 2), 2)} millones de personas"
        return f"{_es(round_half_up(value, 0), 0)} personas"
    if abs(value) >= 1_000_000:
        return f"{_es(round_half_up(value / 1_000_000, 2), 2)} millones" + (f" {u}" if u else "")
    return fmt_es(value, 2) + (f" {u}" if u else "")


def exact_str(value: float) -> str:
    """Valor original exacto para citas (`passage`): sin notación científica ni redondeo (4458759.0 → 4458759)."""
    d = Decimal(str(value))
    text = format(d, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
