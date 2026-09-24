"""Linhas e totais do relatório de retenções, sem banco."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.domain.retencoes import montar_linha, montar_linhas, totalizar
from tests.apoio_notas_ret import NotaRel, d, nota_consistente, nota_do_audio


def test_linha_da_nota_do_audio_carrega_a_analise() -> None:
    linha = montar_linha(nota_do_audio())
    assert linha.analise.situacao == "retencao_nao_abatida"
    assert linha.analise.liquido_estrito == d("11700.00")
    assert linha.analise.liquido_ampliado == d("11262.00")
    assert linha.irrf == d("180.00")


def test_issqn_so_aparece_quando_a_nota_o_marca_como_retido() -> None:
    nao_retido = montar_linha(nota_consistente(valor_issqn=d("50.00"), issqn_retido=False))
    retido = montar_linha(nota_consistente(
        valor_issqn=d("50.00"), issqn_retido=True, valor_liquido_declarado=d("450.00")))
    assert nao_retido.issqn_retido is None
    assert retido.issqn_retido == d("50.00")


def test_as_notas_que_pedem_atencao_vem_primeiro_mesmo_sendo_mais_antigas() -> None:
    antiga_com_problema = nota_do_audio(
        chave_acesso="9" * 50, data_geracao=dt.datetime(2026, 1, 5))
    nova_consistente = nota_consistente(data_geracao=dt.datetime(2026, 9, 1))
    linhas = montar_linhas([nova_consistente, antiga_com_problema])
    assert [linha.chave_acesso for linha in linhas] == ["9" * 50, "2" * 50]


def test_dentro_do_mesmo_grupo_as_mais_novas_primeiro() -> None:
    a = nota_consistente(chave_acesso="a" * 50, data_geracao=dt.datetime(2026, 3, 1))
    b = nota_consistente(chave_acesso="b" * 50, data_geracao=dt.datetime(2026, 8, 1))
    assert [x.chave_acesso for x in montar_linhas([a, b])] == ["b" * 50, "a" * 50]


def test_nota_sem_data_de_geracao_nao_quebra_a_ordenacao() -> None:
    sem_data = NotaRel(chave_acesso="c" * 50, data_geracao=None,
                       valor_servico=d("1.00"), valor_liquido_declarado=d("1.00"))
    assert len(montar_linhas([sem_data, nota_consistente()])) == 2


def test_somente_divergentes_filtra_pela_analise() -> None:
    linhas = montar_linhas([nota_consistente(), nota_do_audio()], somente_divergentes=True)
    assert [linha.chave_acesso for linha in linhas] == ["1" * 50]


# ------------------------------------------------------------------ totais ---


def test_totais_da_nota_do_audio() -> None:
    t = totalizar(montar_linhas([nota_do_audio()]))
    assert t.notas == 1 and t.com_atencao == 1
    assert t.irrf == d("180.00")
    assert t.contrib_sociais_retidas == d("120.00")
    assert t.nao_abatido_estrito == d("300.00")
    assert t.nao_abatido_ampliado == d("738.00")


def test_pis_e_cofins_ficam_fora_do_total_retido() -> None:
    """São 'débito de apuração própria' no DANFSe: somá-los ao retido decidiria
    em silêncio a discussão fiscal."""
    t = totalizar(montar_linhas([nota_do_audio()]))
    assert t.retencoes_estritas == d("300.00")  # IRRF + contribuições, sem PIS/COFINS
    assert t.pis_debito == d("78.00")
    assert t.cofins_debito == d("360.00")


def test_nota_consistente_nao_entra_no_nao_abatido() -> None:
    t = totalizar(montar_linhas([nota_do_audio(), nota_consistente()]))
    assert t.notas == 2 and t.com_atencao == 1
    assert t.nao_abatido_estrito == d("300.00")
    assert t.por_analise["consistente"] == 1
    assert t.por_analise["retencao_nao_abatida"] == 1


def test_contagem_por_analise_cobre_todas_as_situacoes() -> None:
    t = totalizar([])
    assert set(t.por_analise) == {
        "consistente", "retencao_nao_abatida", "liquido_acima_do_bruto",
        "liquido_abaixo_do_esperado", "indeterminado",
    }


def test_totais_de_uma_lista_vazia_sao_zero_e_nao_none() -> None:
    t = totalizar([])
    assert t.notas == 0 and t.com_atencao == 0
    for valor in (t.valor_servico, t.irrf, t.retencoes_estritas, t.nao_abatido_estrito):
        assert valor == Decimal("0.00")


def test_valor_ausente_nao_vira_zero_na_linha_mas_soma_zero_no_total() -> None:
    sem_irrf = nota_consistente()
    linha = montar_linha(sem_irrf)
    assert linha.irrf is None
    assert totalizar([linha]).irrf == d("0.00")
