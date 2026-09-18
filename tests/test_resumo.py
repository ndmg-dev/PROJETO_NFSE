"""Cálculo do resumo (spec §5.1). Sem banco: o domínio é puro."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.core.dinheiro import dinheiro, formatar_brl
from app.domain.resumo import calcular_resumo


@dataclass(frozen=True)
class Nota:
    situacao: str
    valor_servico: Decimal | None


def n(valor: str | None, situacao: str = "Normal") -> Nota:
    return Nota(situacao=situacao, valor_servico=dinheiro(valor) if valor else None)


def test_sem_notas_emite_as_tres_situacoes_zeradas() -> None:
    r = calcular_resumo([])
    assert [linha.situacao for linha in r.linhas] == ["Normal", "Cancelada", "Substituída"]
    assert all(linha.quantidade == 0 and linha.valor == Decimal("0.00") for linha in r.linhas)
    assert r.total.quantidade == 0


def test_agrega_por_situacao() -> None:
    r = calcular_resumo([
        n("100.00"), n("50.50"),
        n("30.00", "Cancelada"),
        n("10.00", "Substituída"),
    ])
    assert r.por_situacao("Normal") .quantidade == 2
    assert r.por_situacao("Normal").valor == Decimal("150.50")
    assert r.por_situacao("Cancelada").valor == Decimal("30.00")
    assert r.total.quantidade == 4
    assert r.total.valor == Decimal("190.50")


def test_total_e_a_soma_das_linhas() -> None:
    r = calcular_resumo([n("0.10"), n("0.20"), n("0.30", "Cancelada")])
    assert r.total.valor == sum((linha.valor for linha in r.linhas), Decimal(0))


def test_nota_de_valor_zero_conta_na_quantidade() -> None:
    """38% das notas da referência valem R$ 0,00 — não é caso de borda."""
    r = calcular_resumo([n("0"), n("0"), n("100.00")])
    assert r.por_situacao("Normal").quantidade == 3
    assert r.por_situacao("Normal").valor == Decimal("100.00")


def test_valor_ausente_conta_na_quantidade_mas_nao_no_total() -> None:
    """A nota existe; o valor é que não foi extraído. Sumir com ela mentiria."""
    r = calcular_resumo([n(None), n("100.00")])
    assert r.total.quantidade == 2
    assert r.total.valor == Decimal("100.00")


def test_situacao_desconhecida_para_em_vez_de_sumir_com_a_nota() -> None:
    with pytest.raises(ValueError, match="fora do layout"):
        calcular_resumo([n("10.00", "Inutilizada")])


def test_o_caso_da_ab_engenharia() -> None:
    """Critério de aceite da spec §10: 78 notas, R$ 198.227,91."""
    valores = [
        "165800.21", "15569.60", "7855.98", "6571.86", "1900.15",
        "245.00", "165.00", "67.44", "52.67",
    ] + ["0.00"] * 69
    r = calcular_resumo([n(v) for v in valores])
    assert r.total.quantidade == 78
    assert r.total.valor == Decimal("198227.91")
    assert formatar_brl(r.total.valor) == "198.227,91"
    assert r.por_situacao("Cancelada").quantidade == 0
