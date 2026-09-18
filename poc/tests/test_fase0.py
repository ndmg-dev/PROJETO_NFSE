"""Testes das partes puras da Fase 0 — tudo que não depende do contrato do ADN.

O que NÃO é testado aqui, de propósito: o mapeamento dos campos da resposta e
das tags do XML. Esses vivem no bloco HIPÓTESES e só podem ser fixados contra
uma resposta real (spec §3.2, §10 "Contrato").
"""

from __future__ import annotations

import base64
import gzip
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fase0_dfe import (  # noqa: E402
    BACKOFF_MAX_S,
    CANDIDATOS_LOTE,
    ContratoDesconhecido,
    Documento,
    achar_texto,
    decodificar_conteudo,
    espera_backoff,
    exigir_chave,
    extrair_chave_acesso,
    interpretar_xml,
    moeda,
    normalizar_cnpj,
    normalizar_competencia,
    para_decimal,
)

CHAVE = "2" * 50


# --------------------------------------------------------------- dinheiro ---


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("100.50", Decimal("100.50")),
        ("1.234,56", Decimal("1234.56")),  # pt-BR
        ("0", Decimal("0")),
        ("0.00", Decimal("0.00")),
        ("  42 ", Decimal("42")),
        ("-15.75", Decimal("-15.75")),
        ("60000", Decimal("60000")),
    ],
)
def test_para_decimal_converte(texto: str, esperado: Decimal) -> None:
    assert para_decimal(texto) == esperado


@pytest.mark.parametrize("texto", [None, "", "   ", "abc", "R$"])
def test_para_decimal_recusa_lixo(texto: str | None) -> None:
    assert para_decimal(texto) is None


def test_nenhum_float_no_caminho_do_dinheiro() -> None:
    """Regra 4: valor fiscal nunca passa por float."""
    assert isinstance(para_decimal("198227.91"), Decimal)


def test_soma_decimal_nao_tem_ruido_de_ponto_flutuante() -> None:
    """O caso da spec §5.1: float dá 198227.90999999997."""
    parcelas = [Decimal("165800.21"), Decimal("15569.60"), Decimal("7855.98"),
                Decimal("6571.86"), Decimal("1900.15"), Decimal("245.00"),
                Decimal("165.00"), Decimal("67.44"), Decimal("52.67"), Decimal("0.00")]
    assert sum(parcelas, Decimal(0)) == Decimal("198227.91")


def test_moeda_formata_pt_br() -> None:
    assert moeda(Decimal("198227.91")) == "198.227,91"
    assert moeda(Decimal("0")) == "0,00"
    assert moeda(Decimal("9.99")) == "9,99"
    assert moeda(Decimal("-1234567.5")) == "-1.234.567,50"


# ------------------------------------------------------------ competência ---


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("2026-08-01", "2026-08"),
        ("2026-08", "2026-08"),
        ("08/2026", "2026-08"),
        ("2026-08-31T10:00:00-03:00", "2026-08"),
    ],
)
def test_normalizar_competencia(texto: str, esperado: str) -> None:
    assert normalizar_competencia(texto) == esperado


@pytest.mark.parametrize("texto", [None, "", "agosto", "31/08"])
def test_normalizar_competencia_recusa(texto: str | None) -> None:
    assert normalizar_competencia(texto) is None


def test_normalizar_cnpj() -> None:
    assert normalizar_cnpj("07.199.546/0001-62") == "07199546000162"
    assert normalizar_cnpj(None) == ""


# --------------------------------------------------------------- backoff ---


def test_backoff_respeita_retry_after() -> None:
    assert espera_backoff(0, "30") == 30.0


def test_backoff_limita_retry_after_absurdo() -> None:
    assert espera_backoff(0, "99999") == BACKOFF_MAX_S


def test_backoff_ignora_retry_after_em_data_http() -> None:
    """Retry-After pode vir como data; caímos no exponencial em vez de quebrar."""
    assert 0.0 <= espera_backoff(0, "Wed, 21 Oct 2026 07:28:00 GMT") <= 1.0


def test_backoff_cresce_e_tem_jitter() -> None:
    amostras = [espera_backoff(5, None) for _ in range(200)]
    assert all(0.0 <= a <= BACKOFF_MAX_S for a in amostras)
    assert len(set(amostras)) > 1, "sem jitter: todas as esperas iguais"


def test_backoff_nunca_passa_do_teto() -> None:
    assert all(espera_backoff(t, None) <= BACKOFF_MAX_S for t in range(20))


# ------------------------------------------------------- conteúdo do DF-e ---


def test_decodifica_xml_puro() -> None:
    assert decodificar_conteudo("<NFSe/>") == b"<NFSe/>"


def test_decodifica_base64() -> None:
    xml = b"<NFSe><infNFSe/></NFSe>"
    assert decodificar_conteudo(base64.b64encode(xml).decode()) == xml


def test_decodifica_base64_com_gzip() -> None:
    xml = b"<NFSe><infNFSe/></NFSe>"
    empacotado = base64.b64encode(gzip.compress(xml)).decode()
    assert decodificar_conteudo(empacotado) == xml


def test_decodifica_xml_com_declaracao() -> None:
    xml = b'<?xml version="1.0"?><NFSe/>'
    assert decodificar_conteudo(xml.decode()) == xml


# ------------------------------------------------------------- namespaces ---


def test_achar_texto_ignora_namespace_inesperado() -> None:
    """Regra 6: XML com namespace inesperado não pode quebrar o parser."""
    raiz = ET.fromstring('<NFSe xmlns="http://urn.inesperado/v99"><dCompet>2026-08-01</dCompet></NFSe>')
    assert achar_texto(raiz, ("dCompet",)) == "2026-08-01"


def test_achar_texto_sem_namespace() -> None:
    raiz = ET.fromstring("<NFSe><dCompet>2026-08-01</dCompet></NFSe>")
    assert achar_texto(raiz, ("dCompet",)) == "2026-08-01"


def test_achar_texto_ausente() -> None:
    raiz = ET.fromstring("<NFSe/>")
    assert achar_texto(raiz, ("dCompet",)) is None


def test_achar_texto_ignora_vazio() -> None:
    raiz = ET.fromstring("<NFSe><dCompet>   </dCompet></NFSe>")
    assert achar_texto(raiz, ("dCompet",)) is None


# ---------------------------------------------------------- chave acesso ---


def test_chave_em_atributo_id() -> None:
    raiz = ET.fromstring(f'<NFSe><infNFSe Id="NFS{CHAVE}"/></NFSe>')
    assert extrair_chave_acesso(raiz, b"") == CHAVE


def test_chave_em_texto() -> None:
    raiz = ET.fromstring(f"<NFSe><chNFSe>{CHAVE}</chNFSe></NFSe>")
    assert extrair_chave_acesso(raiz, b"") == CHAVE


def test_chave_ausente() -> None:
    raiz = ET.fromstring("<NFSe><nNFSe>123</nNFSe></NFSe>")
    assert extrair_chave_acesso(raiz, b"<NFSe/>") is None


def test_nome_arquivo_sem_chave_nao_colide() -> None:
    a = Documento(nsu=7, xml=b"<a/>", tipo_bruto=None)
    b = Documento(nsu=7, xml=b"<b/>", tipo_bruto=None)
    assert a.nome_arquivo != b.nome_arquivo
    assert a.nome_arquivo.startswith("sem-chave-nsu000000000007-")


def test_nome_arquivo_usa_chave() -> None:
    d = Documento(nsu=1, xml=b"<a/>", tipo_bruto=None, chave_acesso=CHAVE)
    assert d.nome_arquivo == f"{CHAVE}.xml"


# ----------------------------------------------------- interpretação NFSe ---


def nfse_xml(valor: str = "1500.00", competencia: str = "2026-08-01",
             tomador: str = "07199546000162") -> bytes:
    return f"""<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
      <infNFSe Id="NFS{CHAVE}">
        <DPS><infDPS>
          <dCompet>{competencia}</dCompet>
          <toma><CNPJ>{tomador}</CNPJ></toma>
          <valores><vServ>{valor}</vServ></valores>
        </infDPS></DPS>
      </infNFSe>
    </NFSe>""".encode()


def test_interpreta_nfse_completa() -> None:
    d = interpretar_xml(Documento(nsu=1, xml=nfse_xml(), tipo_bruto="NFSe"))
    assert d.eh_evento is False
    assert d.chave_acesso == CHAVE
    assert d.competencia == "2026-08"
    assert d.valor_servico == Decimal("1500.00")
    assert d.tomador_cnpj == "07199546000162"
    assert d.campos_faltando == []


def test_interpreta_nota_de_valor_zero() -> None:
    """Caso degenerado real: 3 notas de Barueri na referência valem R$ 0,00."""
    d = interpretar_xml(Documento(nsu=1, xml=nfse_xml(valor="0"), tipo_bruto="NFSe"))
    assert d.valor_servico == Decimal("0")
    assert "valor_servico" not in d.campos_faltando


def test_campos_ausentes_sao_reportados_nao_inventados() -> None:
    xml = b'<NFSe><infNFSe Id="NFS%s"/></NFSe>' % CHAVE.encode()
    d = interpretar_xml(Documento(nsu=1, xml=xml, tipo_bruto="NFSe"))
    assert d.valor_servico is None
    assert set(d.campos_faltando) == {"competencia", "valor_servico", "tomador_cnpj"}


def test_evento_nao_entra_no_somatorio() -> None:
    xml = b"<EventoNFSe><infEvento><tpEvento>101101</tpEvento></infEvento></EventoNFSe>"
    d = interpretar_xml(Documento(nsu=1, xml=xml, tipo_bruto=None))
    assert d.eh_evento is True
    assert d.valor_servico is None


def test_evento_detectado_pelo_tipo_do_lote() -> None:
    d = interpretar_xml(Documento(nsu=1, xml=b"<qualquer/>", tipo_bruto="Evento"))
    assert d.eh_evento is True


def test_xml_invalido_nao_derruba_a_varredura() -> None:
    d = interpretar_xml(Documento(nsu=1, xml=b"nao sou xml", tipo_bruto="NFSe"))
    assert any(c.startswith("xml-invalido") for c in d.campos_faltando)


def test_tomador_diferente_do_consultado() -> None:
    d = interpretar_xml(Documento(nsu=1, xml=nfse_xml(tomador="11111111000111"), tipo_bruto="NFSe"))
    assert d.tomador_cnpj == "11111111000111"


# -------------------------------------------------------------- contrato ---


def test_exigir_chave_encontra() -> None:
    assert exigir_chave({"loteDFe": []}, CANDIDATOS_LOTE, "lote", None) == "loteDFe"


def test_exigir_chave_para_em_vez_de_chutar() -> None:
    """Regra 3: contrato desconhecido é parada, não palpite."""
    with pytest.raises(ContratoDesconhecido) as exc:
        exigir_chave({"nomeReal": 1}, CANDIDATOS_LOTE, "lote", None)
    assert "nomeReal" in str(exc.value)
    assert "HIPÓTESES" in str(exc.value)
