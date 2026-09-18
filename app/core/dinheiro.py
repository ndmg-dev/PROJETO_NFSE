"""Valores fiscais. Nenhum `float` atravessa este módulo — nem na entrada.

Regra do projeto: dinheiro é `Decimal` no Python e `numeric` no Postgres.
Alíquota idem. A defesa aqui é ativa: passar um `float` levanta `TypeError` em
vez de converter silenciosamente, porque `float("0.1") + float("0.2")` já
nasceu errado e nenhum arredondamento posterior conserta.

O caso concreto que motiva isto está na planilha do portal: o total de
agosto/2026 da AB Engenharia sai como `198227.90999999997`. Com `Decimal`,
fecha em `198227.91`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation, localcontext
from typing import Final

CENTAVOS: Final = Decimal("0.01")
QUATRO_CASAS: Final = Decimal("0.0001")

# numeric(15,2) e numeric(7,4) no schema — os limites são do banco, não nossos.
MAX_VALOR: Final = Decimal("9" * 13 + ".99")
MAX_ALIQUOTA: Final = Decimal("999.9999")

_SEPARADORES = re.compile(r"[\s ]")


class ValorInvalidoError(ValueError):
    """Texto que não representa um valor fiscal utilizável."""


def _recusar_float(valor: object, origem: str) -> None:
    if isinstance(valor, float):
        raise TypeError(
            f"{origem}: recebeu float ({valor!r}). Valor fiscal nunca passa por "
            "float — use str ou Decimal. Converter aqui esconderia o erro."
        )


def dinheiro(valor: str | int | Decimal) -> Decimal:
    """Converte para `Decimal` com 2 casas, arredondando meio-para-par.

    Aceita `1234.56` e o formato pt-BR `1.234,56`. Recusa `float`.
    """
    _recusar_float(valor, "dinheiro()")
    bruto = _para_decimal(valor, "dinheiro()")
    with localcontext() as ctx:
        ctx.prec = 28
        quantizado = bruto.quantize(CENTAVOS)
    if abs(quantizado) > MAX_VALOR:
        raise ValorInvalidoError(
            f"dinheiro(): {quantizado} não cabe em numeric(15,2)."
        )
    return quantizado


def aliquota(valor: str | int | Decimal) -> Decimal:
    """Converte para `Decimal` com 4 casas — numeric(7,4) no schema."""
    _recusar_float(valor, "aliquota()")
    bruto = _para_decimal(valor, "aliquota()")
    with localcontext() as ctx:
        ctx.prec = 28
        quantizado = bruto.quantize(QUATRO_CASAS)
    if abs(quantizado) > MAX_ALIQUOTA:
        raise ValorInvalidoError(
            f"aliquota(): {quantizado} não cabe em numeric(7,4)."
        )
    return quantizado


def _para_decimal(valor: str | int | Decimal, origem: str) -> Decimal:
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ValorInvalidoError(f"{origem}: {valor} não é finito.")
        return valor
    if isinstance(valor, int):
        return Decimal(valor)

    texto = _SEPARADORES.sub("", valor).replace("R$", "")
    if not texto:
        raise ValorInvalidoError(f"{origem}: texto vazio.")
    if "," in texto:  # pt-BR: milhar com ponto, decimal com vírgula
        texto = texto.replace(".", "").replace(",", ".")
    try:
        convertido = Decimal(texto)
    except InvalidOperation:
        raise ValorInvalidoError(f"{origem}: {valor!r} não é um valor.") from None
    if not convertido.is_finite():
        raise ValorInvalidoError(f"{origem}: {valor!r} não é finito.")
    return convertido


def dinheiro_opcional(valor: str | int | Decimal | None) -> Decimal | None:
    """Campo fiscal opcional ausente é `None`, nunca zero.

    A distinção importa: ISSQN ausente no XML não é ISSQN de R$ 0,00, e um
    relatório que os confunde mente sobre retenção.
    """
    if valor is None:
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    return dinheiro(valor)


def somar(valores: Iterable[Decimal]) -> Decimal:
    """Soma valores fiscais. `sum()` nu começa em `int` 0 e aceita float."""
    total = Decimal("0.00")
    for v in valores:
        _recusar_float(v, "somar()")
        if not isinstance(v, Decimal):
            raise TypeError(f"somar(): esperava Decimal, recebeu {type(v).__name__}.")
        total += v
    return total.quantize(CENTAVOS)


def formatar_brl(valor: Decimal) -> str:
    """`Decimal('198227.91')` -> `'198.227,91'`. Formatação só na borda."""
    _recusar_float(valor, "formatar_brl()")
    if not isinstance(valor, Decimal):
        raise TypeError("formatar_brl(): esperava Decimal.")
    inteiro, _, centavos = f"{valor.quantize(CENTAVOS):.2f}".partition(".")
    sinal = "-" if inteiro.startswith("-") else ""
    inteiro = inteiro.lstrip("-")
    grupos: list[str] = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return f"{sinal}{'.'.join(grupos)},{centavos}"


def formatar_aliquota(valor: Decimal) -> str:
    """`Decimal('2.5000')` -> `'2,5000'`."""
    _recusar_float(valor, "formatar_aliquota()")
    return f"{valor.quantize(QUATRO_CASAS):.4f}".replace(".", ",")
