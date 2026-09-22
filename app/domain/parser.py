"""Parser do XML da NFS-e nacional (spec §7).

ESTADO: os nomes de tag são HIPÓTESE, não fato.

O layout oficial está no XSD do padrão nacional, que ainda não foi confrontado
com um XML real — ver app/adn/contrato.py. Por isso o parser nunca preenche um
campo por adivinhação: ou extrai, ou registra em `campos_ausentes`. Um campo
ausente não vira zero, string vazia ou data de hoje.

A diferença importa: ISSQN ausente não é ISSQN de R$ 0,00, e um relatório de
retenções que confunde os dois mente para o cliente.

Sem I/O: recebe bytes, devolve DTO. É testável sem rede e sem banco.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Final
from xml.etree import ElementTree as ET

from app.core.dinheiro import ValorInvalidoError, aliquota, dinheiro

TAM_CHAVE: Final = 50

# HIPÓTESES — confirmar contra o XSD oficial e o primeiro XML real.
TAGS: Final[dict[str, tuple[str, ...]]] = {
    "numero": ("nNFSe", "NumeroNFSe", "numero"),
    "data_geracao": ("dhProc", "dhEmi", "DataEmissao", "dataGeracao"),
    "competencia": ("dCompet", "Competencia", "competencia"),
    "valor_servico": ("vServ", "ValorServico", "vServPrest"),
    "desconto_incondicionado": ("vDescIncond", "DescontoIncondicionado"),
    "base_calculo": ("vBC", "BaseCalculo"),
    "aliquota_issqn": ("pAliq", "Aliquota", "aliquotaIssqn"),
    "valor_issqn": ("vISSQN", "ValorIssqn"),
    "municipio_incidencia": ("cMunIncid", "cLocIncid", "MunicipioIncidencia"),
    "cod_tributacao_nacional": ("cTribNac", "CodigoTributacaoNacional"),
    "item_nbs": ("cNBS", "ItemNBS"),
    "descricao_servico": ("xDescServ", "Discriminacao", "DescricaoServico"),
    "informacoes_complementares": ("xInfComp", "InformacoesComplementares"),
}
TAGS_BLOCO: Final[dict[str, tuple[str, ...]]] = {
    "prestador": ("prest", "emit", "Prestador", "Emitente"),
    "tomador": ("toma", "Tomador"),
}
TAGS_CNPJ: Final[tuple[str, ...]] = ("CNPJ", "Cnpj", "cnpj")
TAGS_CPF: Final[tuple[str, ...]] = ("CPF", "Cpf", "cpf")
TAGS_NOME: Final[tuple[str, ...]] = ("xNome", "RazaoSocial", "Nome", "xFant")
TAGS_IM: Final[tuple[str, ...]] = ("IM", "InscricaoMunicipal", "im")
TAGS_EVENTO: Final[tuple[str, ...]] = ("tpEvento", "TipoEvento", "codEvento")
TAGS_MOTIVO: Final[tuple[str, ...]] = ("xMotivo", "Motivo", "xJust", "justificativa")


class XmlInvalido(ValueError):
    """Não é XML bem formado. Vai para a fila morta com o bruto preservado."""


@dataclass
class NFSeDTO:
    chave_acesso: str | None = None
    numero: str | None = None
    data_geracao: datetime | None = None
    competencia: date | None = None
    prestador_cnpj: str | None = None
    prestador_nome: str | None = None
    prestador_im: str | None = None
    tomador_cnpj: str | None = None
    tomador_nome: str | None = None
    tomador_im: str | None = None
    municipio_incidencia: str | None = None
    valor_servico: Decimal | None = None
    desconto_incondicionado: Decimal | None = None
    base_calculo: Decimal | None = None
    aliquota_issqn: Decimal | None = None
    valor_issqn: Decimal | None = None
    cod_tributacao_nacional: str | None = None
    item_nbs: str | None = None
    descricao_servico: str | None = None
    informacoes_complementares: str | None = None
    campos_ausentes: list[str] = field(default_factory=list)

    @property
    def utilizavel(self) -> bool:
        """Mínimo para a nota valer alguma coisa num relatório."""
        return bool(self.chave_acesso) and self.valor_servico is not None

    def papel_de(self, cnpj: str) -> str | None:
        if cnpj and cnpj == self.tomador_cnpj:
            return "tomador"
        if cnpj and cnpj == self.prestador_cnpj:
            return "prestador"
        return None


@dataclass
class EventoDTO:
    chave_acesso: str | None = None
    tipo_evento: str | None = None
    data_evento: datetime | None = None
    autor: str | None = None
    motivo: str | None = None
    campos_ausentes: list[str] = field(default_factory=list)


def _nome_local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _raiz(xml: bytes) -> ET.Element:
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise XmlInvalido(f"XML mal formado: {exc}") from None


def _texto(raiz: ET.Element, tags: tuple[str, ...]) -> str | None:
    """Busca pelo nome local, ignorando namespace.

    Namespace inesperado não pode derrubar o parser: a reforma tributária vai
    mudar o layout mais de uma vez até 2033 (spec §11).
    """
    alvos = {t.lower() for t in tags}
    for elemento in raiz.iter():
        if _nome_local(elemento.tag).lower() in alvos and (
            elemento.text and elemento.text.strip()
        ):
            return elemento.text.strip()
    return None


def _bloco(raiz: ET.Element, tags: tuple[str, ...]) -> ET.Element | None:
    alvos = {t.lower() for t in tags}
    for elemento in raiz.iter():
        if _nome_local(elemento.tag).lower() in alvos:
            return elemento
    return None


def extrair_chave(raiz: ET.Element, xml: bytes) -> str | None:
    """A chave da NFS-e nacional tem 50 dígitos. Busca por forma, não por tag."""
    for elemento in raiz.iter():
        for valor in elemento.attrib.values():
            digitos = re.sub(r"\D", "", valor)
            if len(digitos) == TAM_CHAVE:
                return digitos
        if elemento.text:
            texto = elemento.text.strip()
            if len(texto) == TAM_CHAVE and texto.isdigit():
                return texto
    achado = re.search(rb"\b\d{50}\b", xml)
    return achado.group(0).decode() if achado else None


def _data_hora(texto: str | None) -> datetime | None:
    if not texto:
        return None
    limpo = texto.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(limpo)
    except ValueError:
        pass
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(limpo[:10], formato)
        except ValueError:
            continue
    return None


def _competencia(texto: str | None) -> date | None:
    """Competência é sempre o primeiro dia do mês: o dia não tem significado."""
    if not texto:
        return None
    t = texto.strip()
    if m := re.match(r"^(\d{4})-(\d{2})", t):
        return date(int(m.group(1)), int(m.group(2)), 1)
    if m := re.match(r"^(\d{2})/(\d{4})$", t):
        return date(int(m.group(2)), int(m.group(1)), 1)
    return None


def _documento(bloco: ET.Element | None) -> str | None:
    if bloco is None:
        return None
    return _texto(bloco, TAGS_CNPJ) or _texto(bloco, TAGS_CPF)


def parse_nfse(xml: bytes) -> NFSeDTO:
    raiz = _raiz(xml)
    dto = NFSeDTO(chave_acesso=extrair_chave(raiz, xml))
    if dto.chave_acesso is None:
        dto.campos_ausentes.append("chave_acesso")

    dto.numero = _texto(raiz, TAGS["numero"])
    dto.data_geracao = _data_hora(_texto(raiz, TAGS["data_geracao"]))
    dto.competencia = _competencia(_texto(raiz, TAGS["competencia"]))
    dto.municipio_incidencia = _texto(raiz, TAGS["municipio_incidencia"])
    dto.cod_tributacao_nacional = _texto(raiz, TAGS["cod_tributacao_nacional"])
    dto.item_nbs = _texto(raiz, TAGS["item_nbs"])
    dto.descricao_servico = _texto(raiz, TAGS["descricao_servico"])
    dto.informacoes_complementares = _texto(raiz, TAGS["informacoes_complementares"])

    for campo, conversor in (
        ("valor_servico", dinheiro),
        ("desconto_incondicionado", dinheiro),
        ("base_calculo", dinheiro),
        ("valor_issqn", dinheiro),
        ("aliquota_issqn", aliquota),
    ):
        bruto = _texto(raiz, TAGS[campo])
        if bruto is None:
            continue
        try:
            setattr(dto, campo, conversor(bruto))
        except ValorInvalidoError:
            dto.campos_ausentes.append(f"{campo}:ilegivel")

    prestador = _bloco(raiz, TAGS_BLOCO["prestador"])
    dto.prestador_cnpj = _documento(prestador)
    dto.prestador_nome = _texto(prestador, TAGS_NOME) if prestador is not None else None
    dto.prestador_im = _texto(prestador, TAGS_IM) if prestador is not None else None

    tomador = _bloco(raiz, TAGS_BLOCO["tomador"])
    dto.tomador_cnpj = _documento(tomador)
    dto.tomador_nome = _texto(tomador, TAGS_NOME) if tomador is not None else None
    dto.tomador_im = _texto(tomador, TAGS_IM) if tomador is not None else None

    for obrigatorio in (
        "numero", "data_geracao", "competencia", "valor_servico",
        "prestador_cnpj", "tomador_cnpj",
    ):
        if getattr(dto, obrigatorio) is None:
            dto.campos_ausentes.append(obrigatorio)

    return dto


def parse_evento(xml: bytes) -> EventoDTO:
    raiz = _raiz(xml)
    dto = EventoDTO(
        chave_acesso=extrair_chave(raiz, xml),
        tipo_evento=_texto(raiz, TAGS_EVENTO),
        data_evento=_data_hora(_texto(raiz, TAGS["data_geracao"])),
        autor=_documento(_bloco(raiz, TAGS_BLOCO["prestador"]))
        or _texto(raiz, TAGS_CNPJ),
        motivo=_texto(raiz, TAGS_MOTIVO),
    )
    for obrigatorio in ("chave_acesso", "tipo_evento"):
        if getattr(dto, obrigatorio) is None:
            dto.campos_ausentes.append(obrigatorio)
    return dto


def inspecionar_layout(xml: bytes) -> str:
    """Árvore de tags do XML — fecha as hipóteses sem adivinhação.

    Usado pelo modo --inspecionar-xml da PoC e por quem for confirmar o
    layout contra um documento real.
    """
    raiz = _raiz(xml)
    linhas: list[str] = []

    def caminhar(elemento: ET.Element, nivel: int) -> None:
        texto = (elemento.text or "").strip()
        resumo = f" = {texto[:60]}" if texto else ""
        atributos = f" {dict(elemento.attrib)}" if elemento.attrib else ""
        linhas.append("  " * nivel + _nome_local(elemento.tag) + atributos + resumo)
        for filho in elemento:
            caminhar(filho, nivel + 1)

    caminhar(raiz, 0)
    return "\n".join(linhas)
