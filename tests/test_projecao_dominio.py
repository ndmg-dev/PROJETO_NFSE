"""Decisão de projeção, sem banco (app/domain/projecao.py)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.parser import parse_evento, parse_nfse
from app.domain.projecao import (
    NotaProjetavel,
    Rejeicao,
    decidir_evento,
    decidir_projecao,
    resolver_papel,
)
from tests.apoio_xml import RETENCOES_DA_NOTA_DO_AUDIO, xml_evento, xml_nota

EMPRESA = "07199546000162"
OUTRO = "11222333000181"
CHAVE = "3" * 50


def decidir(xml: bytes, cnpj: str = EMPRESA) -> NotaProjetavel | Rejeicao:
    return decidir_projecao(parse_nfse(xml), cnpj)


# ------------------------------------------------------------------ papel ---


def test_empresa_tomadora() -> None:
    r = decidir(xml_nota(CHAVE, tomador=EMPRESA, prestador=OUTRO))
    assert isinstance(r, NotaProjetavel) and r.papel == "tomador"


def test_empresa_prestadora() -> None:
    r = decidir(xml_nota(CHAVE, tomador=OUTRO, prestador=EMPRESA))
    assert isinstance(r, NotaProjetavel) and r.papel == "prestador"


def test_cnpj_da_empresa_formatado_ainda_casa() -> None:
    r = decidir(xml_nota(CHAVE), cnpj="07.199.546/0001-62")
    assert isinstance(r, NotaProjetavel) and r.papel == "tomador"


def test_mesmo_cnpj_nos_dois_lados_vale_tomador() -> None:
    r = decidir(xml_nota(CHAVE, tomador=EMPRESA, prestador=EMPRESA))
    assert isinstance(r, NotaProjetavel) and r.papel == "tomador"


def test_empresa_que_nao_e_nenhuma_das_partes_e_rejeitada() -> None:
    """Possível intermediário: papel indeterminado, nada de palpite."""
    r = decidir(xml_nota(CHAVE, tomador=OUTRO, prestador="99888777000166"))
    assert isinstance(r, Rejeicao)
    assert "intermediário" in r.motivo


def test_resolver_papel_sem_cnpj_da_empresa() -> None:
    assert resolver_papel(parse_nfse(xml_nota(CHAVE)), "") is None


# ---------------------------------------------------------------- rejeição ---


def test_nota_sem_valor_e_rejeitada_com_o_motivo() -> None:
    r = decidir(xml_nota(CHAVE, sem_valor=True))
    assert isinstance(r, Rejeicao)
    assert "valor do serviço" in r.motivo


def test_nota_sem_chave_e_rejeitada() -> None:
    xml = b"<NFSe><infNFSe><valores><vServ>10.00</vServ></valores></infNFSe></NFSe>"
    r = decidir(xml)
    assert isinstance(r, Rejeicao)
    assert "chave" in r.motivo


def test_valor_zero_e_projetavel() -> None:
    """30 das 78 notas da referência valem R$ 0,00."""
    r = decidir(xml_nota(CHAVE, valor="0"))
    assert isinstance(r, NotaProjetavel)
    assert r.dto.valor_servico == Decimal("0.00")


def test_retencoes_seguem_para_a_projecao() -> None:
    r = decidir(xml_nota(CHAVE, valor="12000.00", extra=RETENCOES_DA_NOTA_DO_AUDIO))
    assert isinstance(r, NotaProjetavel)
    assert r.dto.irrf == Decimal("180.00")
    assert r.dto.pis_debito == Decimal("78.00")
    assert r.dto.valor_liquido_declarado == Decimal("12000.00")


# ------------------------------------------------- documento da contraparte ---


def test_cnpj_da_contraparte_formatado_e_normalizado() -> None:
    r = decidir(xml_nota(CHAVE, prestador="11.222.333/0001-81"))
    assert isinstance(r, NotaProjetavel)
    assert r.dto.prestador_cnpj == "11222333000181"
    assert r.avisos == ()


def test_documento_estrangeiro_nao_derruba_a_nota() -> None:
    """NIF de tomador estrangeiro não cabe em String(14): não grava, avisa, e a
    nota — de que a empresa é prestadora — continua sendo projetada."""
    r = decidir(xml_nota(CHAVE, tomador="12345678", prestador=EMPRESA))
    assert isinstance(r, NotaProjetavel)
    assert r.papel == "prestador"
    assert r.dto.tomador_cnpj is None
    assert any("8 dígitos" in a for a in r.avisos)


def test_cpf_de_11_digitos_e_aceito() -> None:
    r = decidir(xml_nota(CHAVE, prestador="12345678901"))
    assert isinstance(r, NotaProjetavel)
    assert r.dto.prestador_cnpj == "12345678901"


# ----------------------------------------------------------------- eventos ---


def test_evento_de_cancelamento_muda_a_situacao() -> None:
    r = decidir_evento(parse_evento(xml_evento(CHAVE, "101101")))
    assert not isinstance(r, Rejeicao)
    assert r.nova_situacao == "Cancelada"
    assert r.chave_acesso == CHAVE


def test_evento_de_tipo_desconhecido_nao_muda_a_situacao() -> None:
    """Situação errada é pior que ausente: código não mapeado não age."""
    r = decidir_evento(parse_evento(xml_evento(CHAVE, "999999")))
    assert not isinstance(r, Rejeicao)
    assert r.nova_situacao is None
    assert r.tipo_evento == "999999"


def test_evento_sem_chave_ou_sem_tipo_e_rejeitado() -> None:
    assert isinstance(decidir_evento(parse_evento(b"<EventoNFSe><x/></EventoNFSe>")), Rejeicao)
    sem_tipo = f"<EventoNFSe><chNFSe>{CHAVE}</chNFSe></EventoNFSe>".encode()
    assert isinstance(decidir_evento(parse_evento(sem_tipo)), Rejeicao)


@pytest.mark.parametrize("tipo,esperada", [("101101", "Cancelada"), ("105102", "Substituída")])
def test_tabela_de_eventos_hipotese_declarada(tipo: str, esperada: str) -> None:
    """Trava o que a tabela HIPÓTESE diz hoje; mudar exige decidir conscientemente."""
    r = decidir_evento(parse_evento(xml_evento(CHAVE, tipo)))
    assert not isinstance(r, Rejeicao) and r.nova_situacao == esperada
