"""XMLs sintéticos para os testes de projeção.

Seguem os nomes de tag DECLARADOS em app/domain/parser.py, que são hipótese (o
layout real ainda não foi confrontado). Provam a mecânica da projeção, não que o
ADN use estas tags.
"""

from __future__ import annotations

RETENCOES_DA_NOTA_DO_AUDIO = (
    "<vLiq>12000.00</vLiq>"
    "<tribFed><piscofins><vPis>78.00</vPis><vCofins>360.00</vCofins></piscofins>"
    "<vRetIRRF>180.00</vRetIRRF><vRetCSLL>120.00</vRetCSLL></tribFed>"
    "<tpRetISSQN>1</tpRetISSQN>"
)


def xml_nota(
    chave: str,
    *,
    tomador: str = "07199546000162",
    prestador: str = "11222333000181",
    valor: str = "1500.00",
    extra: str = "",
    sem_valor: bool = False,
) -> bytes:
    bloco_valor = "" if sem_valor else f"<vServ>{valor}</vServ>"
    return f"""<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">
      <infNFSe Id="NFS{chave}">
        <nNFSe>{chave[:6]}</nNFSe>
        <dhProc>2026-08-31T14:22:05-03:00</dhProc>
        <DPS><infDPS>
          <dCompet>2026-08-01</dCompet>
          <prest><CNPJ>{prestador}</CNPJ><xNome>PRESTADOR EXEMPLO</xNome></prest>
          <toma><CNPJ>{tomador}</CNPJ><xNome>TOMADOR EXEMPLO</xNome></toma>
          <valores>{bloco_valor}{extra}</valores>
        </infDPS></DPS>
      </infNFSe>
    </NFSe>""".encode()


def xml_evento(chave: str, tipo: str = "101101", data: str = "2026-09-02T10:00:00-03:00") -> bytes:
    return f"""<EventoNFSe><infEvento>
      <chNFSe>{chave}</chNFSe><tpEvento>{tipo}</tpEvento>
      <dhProc>{data}</dhProc><xMotivo>Erro de emissão</xMotivo>
    </infEvento></EventoNFSe>""".encode()
