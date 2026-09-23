"""Análise do valor líquido (spec §5.2).

O caso central vem de uma nota real de honorários advocatícios (R$ 12.000,00)
cujo líquido impresso era igual ao bruto, apesar de IRRF, contribuições sociais,
PIS e COFINS destacados. Aqui ela aparece ANONIMIZADA: partes fictícias, sem
conta bancária nem e-mail — só os valores, que são o que a análise usa.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from app.core.dinheiro import dinheiro
from app.domain.liquido import (
    analisar_liquido,
    extrair_liquido_da_descricao,
)

DESCRICAO_REAL = (
    "Honorarios Advocaticios. Parcela: 0009 Valor líquido: R$ 11.262,00 "
    "Vencimento: 15/05/2026"
)


@dataclass(frozen=True)
class Nota:
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


def d(valor: str) -> Decimal:
    return dinheiro(valor)


def nota_real() -> Nota:
    return Nota(
        valor_servico=d("12000.00"),
        valor_liquido_declarado=d("12000.00"),
        total_retencoes_declarado=None,  # "Total das Retenções: -"
        irrf=d("180.00"),
        contrib_sociais_retidas=d("120.00"),
        pis_debito=d("78.00"),
        cofins_debito=d("360.00"),
        issqn_retido=False,
        descricao_servico=DESCRICAO_REAL,
    )


# --------------------------------------------------------- o caso do áudio ---


def test_nota_real_retencao_nao_abatida() -> None:
    a = analisar_liquido(nota_real())
    assert a.situacao == "retencao_nao_abatida"
    assert a.requer_atencao


def test_nota_real_os_dois_cenarios() -> None:
    a = analisar_liquido(nota_real())
    assert a.retencoes_estritas == d("300.00")  # IRRF + contrib. sociais
    assert a.retencoes_ampliadas == d("738.00")  # + PIS + COFINS
    assert a.liquido_estrito == d("11700.00")
    assert a.liquido_ampliado == d("11262.00")
    assert a.diferenca_estrita == d("300.00")
    assert a.diferenca_ampliada == d("738.00")


def test_nota_real_descricao_corrobora_o_cenario_ampliado() -> None:
    a = analisar_liquido(nota_real())
    assert a.liquido_na_descricao == d("11262.00")
    assert a.cenario_da_descricao == "ampliado"
    assert a.descricao_diverge_do_declarado


def test_nota_real_total_de_retencoes_omitido() -> None:
    assert analisar_liquido(nota_real()).total_retencoes_omitido


def test_o_sistema_nao_escolhe_o_cenario_por_conta_propria() -> None:
    """Se PIS/COFINS foram retidos é decisão fiscal, não do código."""
    a = analisar_liquido(nota_real())
    assert a.liquido_estrito != a.liquido_ampliado
    assert a.situacao == "retencao_nao_abatida"  # vale nos dois cenários


# ---------------------------------------------------------- consistência ---


def test_consistente_quando_bate_com_o_cenario_estrito() -> None:
    n = Nota(**{**nota_real().__dict__, "valor_liquido_declarado": d("11700.00")})
    assert analisar_liquido(n).situacao == "consistente"


def test_consistente_quando_bate_com_o_cenario_ampliado() -> None:
    """Emitente que tratou PIS/COFINS como retidos não errou."""
    n = Nota(**{**nota_real().__dict__, "valor_liquido_declarado": d("11262.00")})
    assert analisar_liquido(n).situacao == "consistente"


def test_sem_retencao_liquido_igual_ao_bruto_e_consistente() -> None:
    n = Nota(valor_servico=d("500.00"), valor_liquido_declarado=d("500.00"))
    a = analisar_liquido(n)
    assert a.situacao == "consistente"
    assert not a.requer_atencao


def test_nota_de_valor_zero_e_consistente() -> None:
    """30 das 78 notas da referência valem R$ 0,00 — não podem alarmar."""
    n = Nota(valor_servico=d("0"), valor_liquido_declarado=d("0"))
    a = analisar_liquido(n)
    assert a.situacao == "consistente"
    assert not a.requer_atencao


def test_so_pis_cofins_de_apuracao_propria_nao_alarma() -> None:
    """Sem retenção rotulada como tal, líquido = bruto é coerente."""
    n = Nota(
        valor_servico=d("1000.00"),
        valor_liquido_declarado=d("1000.00"),
        pis_debito=d("6.50"),
        cofins_debito=d("30.00"),
    )
    a = analisar_liquido(n)
    assert a.situacao == "consistente"
    assert not a.requer_atencao
    assert a.diferenca_ampliada == d("36.50")  # a informação continua visível


# ------------------------------------------------------------ divergências ---


def test_liquido_acima_do_bruto() -> None:
    n = Nota(valor_servico=d("100.00"), valor_liquido_declarado=d("120.00"))
    assert analisar_liquido(n).situacao == "liquido_acima_do_bruto"


def test_liquido_abaixo_do_esperado() -> None:
    n = Nota(**{**nota_real().__dict__, "valor_liquido_declarado": d("9000.00")})
    a = analisar_liquido(n)
    assert a.situacao == "liquido_abaixo_do_esperado"
    assert a.requer_atencao


def test_tolerancia_de_um_centavo() -> None:
    base = nota_real().__dict__
    assert analisar_liquido(Nota(**{**base, "valor_liquido_declarado": d("11700.01")})
                            ).situacao == "consistente"
    assert analisar_liquido(Nota(**{**base, "valor_liquido_declarado": d("11700.02")})
                            ).situacao == "retencao_nao_abatida"


def test_indeterminado_sem_liquido_declarado() -> None:
    n = Nota(**{**nota_real().__dict__, "valor_liquido_declarado": None})
    assert analisar_liquido(n).situacao == "indeterminado"


def test_indeterminado_sem_valor_do_servico() -> None:
    n = Nota(valor_liquido_declarado=d("100.00"), irrf=d("1.00"))
    a = analisar_liquido(n)
    assert a.situacao == "indeterminado"
    assert a.liquido_estrito is None


def test_descricao_igual_ao_declarado_nao_diverge() -> None:
    n = Nota(
        valor_servico=d("11262.00"),
        valor_liquido_declarado=d("11262.00"),
        descricao_servico=DESCRICAO_REAL,
    )
    assert not analisar_liquido(n).descricao_diverge_do_declarado


# -------------------------------------------------------------------- ISSQN ---


def test_issqn_retido_com_valor_abate() -> None:
    n = Nota(
        valor_servico=d("1000.00"),
        valor_liquido_declarado=d("950.00"),
        valor_issqn=d("50.00"),
        issqn_retido=True,
    )
    a = analisar_liquido(n)
    assert a.retencoes_estritas == d("50.00")
    assert a.situacao == "consistente"


def test_issqn_nao_retido_nao_abate() -> None:
    n = Nota(
        valor_servico=d("1000.00"),
        valor_liquido_declarado=d("1000.00"),
        valor_issqn=d("50.00"),
        issqn_retido=False,
    )
    a = analisar_liquido(n)
    assert a.retencoes_estritas == d("0.00")
    assert a.avisos == ()


def test_issqn_retido_sem_valor_avisa() -> None:
    n = Nota(valor_servico=d("1000.00"), valor_liquido_declarado=d("1000.00"),
             issqn_retido=True)
    assert any("sem valor" in aviso for aviso in analisar_liquido(n).avisos)


def test_issqn_sem_informar_retencao_avisa() -> None:
    n = Nota(valor_servico=d("1000.00"), valor_liquido_declarado=d("1000.00"),
             valor_issqn=d("50.00"), issqn_retido=None)
    assert any("não informa" in aviso for aviso in analisar_liquido(n).avisos)


def test_previdencia_retida_entra_no_estrito() -> None:
    n = Nota(valor_servico=d("1000.00"), valor_liquido_declarado=d("890.00"),
             contrib_previd_retida=d("110.00"))
    a = analisar_liquido(n)
    assert a.retencoes_estritas == d("110.00")
    assert a.situacao == "consistente"


# ------------------------------------------------- texto da descrição ---


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Valor líquido: R$ 11.262,00", "11262.00"),
        ("VALOR LÍQUIDO R$ 1.500,50", "1500.50"),
        ("valor liquido: 300,00", "300.00"),
        ("Valor líquido: R$ 11.262,00 ... Valor líquido: R$ 11.262,00", "11262.00"),
        ("Valor líquido: 1234.56", "1234.56"),
    ],
)
def test_extrai_liquido_da_descricao(texto: str, esperado: str) -> None:
    assert extrair_liquido_da_descricao(texto) == Decimal(esperado)


@pytest.mark.parametrize(
    "texto",
    [
        None,
        "",
        "Honorários sem valor algum",
        "Valor líquido: R$ 100,00 e depois Valor líquido: R$ 200,00",  # ambíguo
        "Valor líquido a definir",
        "Valor bruto: R$ 100,00",
    ],
)
def test_nao_adivinha_quando_ha_duvida(texto: str | None) -> None:
    assert extrair_liquido_da_descricao(texto) is None
