"""Nota falsa para os testes do relatório de retenções (sem banco)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from app.core.dinheiro import dinheiro

DESCRICAO_DO_AUDIO = (
    "Honorarios Advocaticios. Parcela: 0009 Valor líquido: R$ 11.262,00 Vencimento: 15/05/2026"
)


def d(valor: str) -> Decimal:
    return dinheiro(valor)


@dataclass(frozen=True)
class NotaRel:
    chave_acesso: str = "1" * 50
    numero: str | None = "3193"
    data_geracao: dt.datetime | None = dt.datetime(2026, 5, 8, 20, 19)
    competencia: dt.date | None = dt.date(2026, 5, 1)
    papel: str = "tomador"
    situacao: str = "Normal"
    prestador_cnpj: str | None = "11222333000181"
    prestador_nome: str | None = "PRESTADOR EXEMPLO"
    tomador_cnpj: str | None = "07199546000162"
    tomador_nome: str | None = "TOMADOR EXEMPLO"
    valor_servico: Decimal | None = None
    valor_liquido_declarado: Decimal | None = None
    total_retencoes_declarado: Decimal | None = None
    irrf: Decimal | None = None
    contrib_sociais_retidas: Decimal | None = None
    contrib_previd_retida: Decimal | None = None
    pis_debito: Decimal | None = None
    cofins_debito: Decimal | None = None
    valor_issqn: Decimal | None = None
    issqn_retido: bool | None = None
    descricao_servico: str | None = None


def nota_do_audio(**mudancas: object) -> NotaRel:
    """A nota que motivou o relatório: retenções destacadas, líquido igual ao bruto."""
    base: dict[str, object] = {
        "valor_servico": d("12000.00"),
        "valor_liquido_declarado": d("12000.00"),
        "total_retencoes_declarado": None,
        "irrf": d("180.00"),
        "contrib_sociais_retidas": d("120.00"),
        "pis_debito": d("78.00"),
        "cofins_debito": d("360.00"),
        "issqn_retido": False,
        "descricao_servico": DESCRICAO_DO_AUDIO,
    }
    return NotaRel(**{**base, **mudancas})  # type: ignore[arg-type]


def nota_consistente(**mudancas: object) -> NotaRel:
    base: dict[str, object] = {
        "chave_acesso": "2" * 50,
        "valor_servico": d("500.00"),
        "valor_liquido_declarado": d("500.00"),
    }
    return NotaRel(**{**base, **mudancas})  # type: ignore[arg-type]
