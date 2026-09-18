"""O contrato do módulo monetário. Se algum destes cair, há float em produção."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.dinheiro import (
    ValorInvalidoError,
    aliquota,
    dinheiro,
    dinheiro_opcional,
    formatar_aliquota,
    formatar_brl,
    somar,
)

# ------------------------------------------------------- recusa de float ---

@pytest.mark.parametrize(
    "fn,arg",
    [
        (dinheiro, 198227.91),
        (dinheiro, 0.0),
        (dinheiro, -1.5),
        (aliquota, 2.5),
        (dinheiro_opcional, 10.0),
        (formatar_brl, 1.0),
    ],
)
def test_float_e_recusado_em_toda_porta_de_entrada(fn, arg) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TypeError, match="float"):
        fn(arg)


def test_somar_recusa_float_no_meio_da_lista() -> None:
    with pytest.raises(TypeError, match="float"):
        somar([Decimal("1.00"), 2.0, Decimal("3.00")])


def test_somar_recusa_int_cru() -> None:
    """int silencioso vira porta de entrada para float via aritmética mista."""
    with pytest.raises(TypeError):
        somar([Decimal("1.00"), 2])


# ---------------------------------------------------------- conversão ------

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("198227.91", Decimal("198227.91")),
        ("1.234,56", Decimal("1234.56")),
        ("R$ 1.234,56", Decimal("1234.56")),
        ("0", Decimal("0.00")),
        ("0,00", Decimal("0.00")),
        ("-15.75", Decimal("-15.75")),
        (60000, Decimal("60000.00")),
        (Decimal("9.99"), Decimal("9.99")),
        ("  42  ", Decimal("42.00")),
    ],
)
def test_dinheiro_converte(entrada, esperado) -> None:  # type: ignore[no-untyped-def]
    assert dinheiro(entrada) == esperado


def test_dinheiro_sempre_tem_duas_casas() -> None:
    assert str(dinheiro("42")) == "42.00"
    assert str(dinheiro(Decimal("1"))) == "1.00"


def test_arredondamento_meio_para_par() -> None:
    """Banker's rounding: o default do Decimal, e o que a RFB usa."""
    assert dinheiro("1.005") == Decimal("1.00")
    assert dinheiro("1.015") == Decimal("1.02")


@pytest.mark.parametrize("lixo", ["", "   ", "abc", "R$", "1,2,3"])
def test_dinheiro_recusa_lixo(lixo: str) -> None:
    with pytest.raises(ValorInvalidoError):
        dinheiro(lixo)


def test_dinheiro_recusa_nan_e_infinito() -> None:
    for v in (Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(ValorInvalidoError):
            dinheiro(v)


def test_dinheiro_recusa_estouro_de_numeric_15_2() -> None:
    with pytest.raises(ValorInvalidoError, match="numeric"):
        dinheiro("99999999999999.99")


# ---------------------------------------------------------- opcional -------

def test_ausente_e_none_nao_zero() -> None:
    """ISSQN ausente não é ISSQN de zero."""
    assert dinheiro_opcional(None) is None
    assert dinheiro_opcional("") is None
    assert dinheiro_opcional("0") == Decimal("0.00")
    assert dinheiro_opcional("0") is not None


# ---------------------------------------------------------- alíquota -------

def test_aliquota_tem_quatro_casas() -> None:
    assert str(aliquota("2.5")) == "2.5000"
    assert str(aliquota("0")) == "0.0000"


def test_aliquota_recusa_estouro_de_numeric_7_4() -> None:
    with pytest.raises(ValorInvalidoError, match="numeric"):
        aliquota("1000")


# ------------------------------------------------- o caso da referência ----

def test_total_da_ab_engenharia_fecha_sem_ruido() -> None:
    """Regressão do bug que a spec §5.1 aponta na planilha do portal."""
    parcelas = [
        "165800.21", "15569.60", "7855.98", "6571.86",
        "1900.15", "245.00", "165.00", "67.44", "52.67", "0.00",
    ]
    total = somar([dinheiro(p) for p in parcelas])
    assert total == Decimal("198227.91")
    assert formatar_brl(total) == "198.227,91"


def test_decimal_e_exato_onde_float_nao_e() -> None:
    """Por que Decimal, em um caso que float erra de fato.

    NOTA: a planilha do portal imprime 198227.90999999997, mas somar os 78
    valores exportados em float dá exatamente 198227.91 em qualquer ordem
    (verificado em 3.000 permutações). A origem do ruído do portal é
    desconhecida — provavelmente soma de valores não arredondados, ou
    aritmética de JavaScript. Não afirmamos o que não reproduzimos.
    """
    parcelas = ["0.70", "0.10", "0.30"]
    assert somar([dinheiro(p) for p in parcelas]) == Decimal("1.10")
    assert sum(float(p) for p in parcelas) == 1.0999999999999999  # float erra aqui


def test_somar_lista_vazia() -> None:
    assert somar([]) == Decimal("0.00")


# --------------------------------------------------------- formatação ------

@pytest.mark.parametrize(
    "valor,esperado",
    [
        ("198227.91", "198.227,91"),
        ("0", "0,00"),
        ("9.99", "9,99"),
        ("1000", "1.000,00"),
        ("-1234567.5", "-1.234.567,50"),
        ("999999999.99", "999.999.999,99"),
    ],
)
def test_formatar_brl(valor: str, esperado: str) -> None:
    assert formatar_brl(dinheiro(valor)) == esperado


def test_formatar_aliquota() -> None:
    assert formatar_aliquota(aliquota("2.5")) == "2,5000"
    assert formatar_aliquota(aliquota("0")) == "0,0000"
