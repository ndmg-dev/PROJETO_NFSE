"""Parser da NFS-e (spec §7 e §10).

LIMITE DESTES TESTES
Os XMLs aqui seguem os nomes de tag DECLARADOS em app/domain/parser.py, que
ainda são hipótese. Eles provam que a mecânica funciona — namespace, casos
degenerados, ausência de campo, conversão monetária — e NÃO que o ADN usa
essas tags. Quando o layout real aparecer, os nomes mudam num lugar só e estes
testes continuam valendo.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.domain.parser import (
    XmlInvalido,
    inspecionar_layout,
    parse_evento,
    parse_nfse,
)

CHAVE = "2" * 50


def nfse(
    valor: str = "1500.00",
    competencia: str = "2026-08-01",
    tomador: str = "07199546000162",
    prestador: str = "14510103000106",
    ns: str = "http://www.sped.fazenda.gov.br/nfse",
    extra: str = "",
) -> bytes:
    return f"""<NFSe xmlns="{ns}">
      <infNFSe Id="NFS{CHAVE}">
        <nNFSe>2600000010997</nNFSe>
        <dhProc>2026-08-31T14:22:05-03:00</dhProc>
        <DPS><infDPS>
          <dCompet>{competencia}</dCompet>
          <prest><CNPJ>{prestador}</CNPJ><xNome>LEAO FERRAMENTAS LTDA.</xNome></prest>
          <toma><CNPJ>{tomador}</CNPJ><xNome>AB ENGENHARIA LTDA</xNome></toma>
          <valores><vServ>{valor}</vServ>{extra}</valores>
        </infDPS></DPS>
      </infNFSe>
    </NFSe>""".encode()


# -------------------------------------------------------------- feliz ------


def test_extrai_os_campos_principais() -> None:
    d = parse_nfse(nfse())
    assert d.chave_acesso == CHAVE
    assert d.numero == "2600000010997"
    assert d.competencia == dt.date(2026, 8, 1)
    assert d.valor_servico == Decimal("1500.00")
    assert d.prestador_cnpj == "14510103000106"
    assert d.tomador_cnpj == "07199546000162"
    assert d.tomador_nome == "AB ENGENHARIA LTDA"
    assert d.campos_ausentes == []
    assert d.utilizavel


def test_data_com_fuso() -> None:
    d = parse_nfse(nfse())
    assert d.data_geracao is not None
    assert d.data_geracao.date() == dt.date(2026, 8, 31)


def test_competencia_e_sempre_o_primeiro_dia_do_mes() -> None:
    assert parse_nfse(nfse(competencia="2026-08-15")).competencia == dt.date(2026, 8, 1)
    assert parse_nfse(nfse(competencia="08/2026")).competencia == dt.date(2026, 8, 1)


def test_papel_do_cnpj_consultado() -> None:
    d = parse_nfse(nfse())
    assert d.papel_de("07199546000162") == "tomador"
    assert d.papel_de("14510103000106") == "prestador"
    assert d.papel_de("99999999999999") is None


# ------------------------------------------------------- degenerados -------


def test_nota_de_valor_zero_e_valida() -> None:
    """38% das notas da referência valem R$ 0,00 — CAIXA Cartões e Pluxee."""
    d = parse_nfse(nfse(valor="0"))
    assert d.valor_servico == Decimal("0.00")
    assert "valor_servico" not in d.campos_ausentes
    assert d.utilizavel


def test_campos_ausentes_sao_listados_nao_inventados() -> None:
    xml = f'<NFSe><infNFSe Id="NFS{CHAVE}"/></NFSe>'.encode()
    d = parse_nfse(xml)
    assert d.valor_servico is None
    assert d.competencia is None
    assert set(d.campos_ausentes) >= {
        "numero", "data_geracao", "competencia", "valor_servico",
        "prestador_cnpj", "tomador_cnpj",
    }
    assert not d.utilizavel


def test_issqn_ausente_nao_vira_zero() -> None:
    """Confundir ausente com zero mentiria no relatório de retenções."""
    d = parse_nfse(nfse())
    assert d.valor_issqn is None
    assert d.aliquota_issqn is None


def test_issqn_zero_e_diferente_de_ausente() -> None:
    d = parse_nfse(nfse(extra="<vISSQN>0</vISSQN>"))
    assert d.valor_issqn == Decimal("0.00")


def test_valor_ilegivel_e_reportado() -> None:
    d = parse_nfse(nfse(valor="mil e quinhentos"))
    assert d.valor_servico is None
    assert "valor_servico:ilegivel" in d.campos_ausentes


def test_namespace_inesperado_nao_derruba() -> None:
    """A reforma tributária vai mudar o layout até 2033 (spec §11)."""
    d = parse_nfse(nfse(ns="http://urn.totalmente.inesperado/v99"))
    assert d.valor_servico == Decimal("1500.00")
    assert d.tomador_cnpj == "07199546000162"


def test_sem_namespace_nenhum() -> None:
    d = parse_nfse(nfse(ns=""))
    assert d.chave_acesso == CHAVE


def test_xml_mal_formado_levanta_erro_proprio() -> None:
    with pytest.raises(XmlInvalido, match="mal formado"):
        parse_nfse(b"<NFSe><sem-fechar>")


def test_xml_vazio() -> None:
    with pytest.raises(XmlInvalido):
        parse_nfse(b"")


def test_cpf_no_lugar_de_cnpj() -> None:
    """Prestador pessoa física aparece na referência (RAQUEL NUNES BARBOSA)."""
    xml = f"""<NFSe><infNFSe Id="NFS{CHAVE}">
      <prest><CPF>12345678901</CPF><xNome>RAQUEL NUNES BARBOSA</xNome></prest>
      <toma><CNPJ>07199546000162</CNPJ></toma>
      <valores><vServ>420.00</vServ></valores></infNFSe></NFSe>""".encode()
    d = parse_nfse(xml)
    assert d.prestador_cnpj == "12345678901"
    assert d.prestador_nome == "RAQUEL NUNES BARBOSA"


def test_valor_em_formato_brasileiro() -> None:
    assert parse_nfse(nfse(valor="1.234,56")).valor_servico == Decimal("1234.56")


# ----------------------------------------------------------- eventos ------


def test_evento_de_cancelamento() -> None:
    xml = f"""<EventoNFSe><infEvento>
      <chNFSe>{CHAVE}</chNFSe><tpEvento>101101</tpEvento>
      <dhProc>2026-09-02T10:00:00-03:00</dhProc>
      <xMotivo>Erro de emissão</xMotivo>
      </infEvento></EventoNFSe>""".encode()
    e = parse_evento(xml)
    assert e.chave_acesso == CHAVE
    assert e.tipo_evento == "101101"
    assert e.motivo == "Erro de emissão"
    assert e.campos_ausentes == []


def test_evento_incompleto_e_reportado() -> None:
    e = parse_evento(b"<EventoNFSe><infEvento/></EventoNFSe>")
    assert set(e.campos_ausentes) == {"chave_acesso", "tipo_evento"}


# ------------------------------------------------------- inspeção ---------


def test_inspecionar_layout_mostra_a_arvore() -> None:
    saida = inspecionar_layout(nfse())
    assert "NFSe" in saida
    assert "dCompet" in saida
    assert "vServ = 1500.00" in saida
