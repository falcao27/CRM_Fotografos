from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def brl(valor):
    try:
        numero = Decimal(valor or 0)
    except (InvalidOperation, TypeError, ValueError):
        numero = Decimal("0")

    texto = f"{numero:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


@register.filter
def moeda_input(valor):
    try:
        numero = Decimal(valor or 0)
    except (InvalidOperation, TypeError, ValueError):
        numero = Decimal("0")
    return f"{numero:.2f}".replace(".", ",")
