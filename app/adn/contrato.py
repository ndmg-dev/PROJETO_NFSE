"""O contrato do ADN.

ESTADO: nomes de campo confirmados pelo Swagger real da produção restrita
(https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html,
lido em 25/09/2026). Ainda NÃO confirmado contra uma resposta com dados
reais (nenhum NSU com documento foi consultado) — os candidatos continuam
como rede de segurança para esse dia.

Envelope de `GET /DFe/{NSU}` (PascalCase, `text/plain` com corpo JSON):
  StatusProcessamento: "REJEICAO" | "NENHUM_DOCUMENTO_LOCALIZADO" | "DOCUMENTOS_LOCALIZADOS"
  LoteDFe: array de DistribuicaoNSU | null
  Alertas, Erros: array de MensagemProcessamento | null
  TipoAmbiente: "PRODUCAO" | "HOMOLOGACAO"
  VersaoAplicativo: string | null
  DataHoraProcessamento: datetime

DistribuicaoNSU: NSU (int|null), ChaveAcesso (str|null), TipoDocumento
(enum: NENHUM/DPS/PEDIDO_REGISTRO_EVENTO/NFSE/EVENTO/CNC), TipoEvento
(enum|null), ArquivoXml (str|null, GZip+base64 por "Padrões técnicos"),
DataHoraGeracao (datetime|null).

NÃO existe campo de "próximo NSU" ou "máximo NSU" no envelope — ao
contrário do que as hipóteses antigas supunham. A paginação só pode vir do
maior NSU dentro do próprio `LoteDFe` (`Lote.maior_nsu`); `max_nsu`/
`ult_nsu` ficam sempre `None` e são só otimização dormente para o dia em
que o ADN passar a expor isso.

Query params de `/DFe/{NSU}`: `cnpjConsulta` (opcional) e `lote` (bool,
default `true`).

Este módulo é a ÚNICA fronteira onde a forma exata da resposta mora. Tudo o
mais no sistema — loop de NSU, checkpoint, backoff, fila morta, detecção de
lacuna — é testado contra a forma declarada aqui.

COMO ACABAR DE FECHAR
1. Rodar uma chamada real (sonda ou app) contra um NSU com documento e
   confirmar que os nomes acima batem com o corpo de verdade, não só com
   o esquema documentado.
2. Se baterem, remover as tuplas `CANDIDATOS_*` e a lógica de fallback.

`extrair_lote` aceita os nomes reais (primeira opção de cada tupla) e cai
para os candidatos antigos só como rede de segurança; se nada casar,
levanta `ContratoDesconhecido` com as chaves reais que vieram — nunca
escolhe em silêncio.
"""

from __future__ import annotations

import base64
import binascii
import gzip
from dataclasses import dataclass
from typing import Final, TypeAlias

# Tipo do JSON do ADN. Explícito em vez de `Any`: o payload é dado externo e
# não confiável, e o mypy passa a cobrar a conversão em cada uso.
# `float` aparece aqui porque JSON tem float — nenhum valor fiscal é lido por
# este caminho: o dinheiro vem do texto do XML, sempre via Decimal.
# (mypy 1.11 ainda não aceita a sintaxe `type X = ...` do PEP 695.)
Json: TypeAlias = (  # noqa: UP040 — ruff quer PEP 695, mypy 1.11 ainda não o aceita
    "str | int | float | bool | None | dict[str, Json] | list[Json]"
)

VERIFICADO: Final = False

CANDIDATOS_LOTE: Final[tuple[str, ...]] = ("LoteDFe", "loteDFe", "documentos", "DFe", "lote")
CANDIDATOS_NSU_DOC: Final[tuple[str, ...]] = ("NSU", "nsu")
CANDIDATOS_CONTEUDO: Final[tuple[str, ...]] = (
    "ArquivoXml", "arquivoXml", "XmlDFe", "xml", "documento",
)
CANDIDATOS_TIPO: Final[tuple[str, ...]] = (
    "TipoDocumento", "tipoDocumento", "tipo", "schema",
)
# O envelope real não tem campo de máximo/último NSU (ver docstring do
# módulo). Mantidas por segurança caso o ADN passe a expor isso.
CANDIDATOS_MAX_NSU: Final[tuple[str, ...]] = ("maxNSU", "MaxNSU", "maximoNSU")
CANDIDATOS_ULT_NSU: Final[tuple[str, ...]] = ("ultNSU", "ultimoNSU", "UltimoNSU")

# Status que indicam fila vazia. 204 é o do modelo de referência da NF-e
# (NT 2014.002); 404 entra por prudência e é tratado como fim, não como erro.
STATUS_FILA_VAZIA: Final[frozenset[int]] = frozenset({204, 404})
STATUS_RETENTAVEL: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})


class ContratoDesconhecido(RuntimeError):
    """A resposta não casou com nenhuma hipótese. Parar é melhor que chutar."""


@dataclass(frozen=True)
class DocumentoDFe:
    nsu: int
    xml: bytes
    tipo: str | None

    @property
    def eh_evento(self) -> bool:
        if self.tipo is not None:
            return "evento" in self.tipo.lower()
        return b"vento" in self.xml[:600]


@dataclass(frozen=True)
class Lote:
    documentos: tuple[DocumentoDFe, ...]
    max_nsu: int | None
    ult_nsu: int | None

    @property
    def maior_nsu(self) -> int | None:
        return max((d.nsu for d in self.documentos), default=None)


def _achar(dados: dict[str, Json], candidatos: tuple[str, ...], papel: str) -> str:
    for c in candidatos:
        if c in dados:
            return c
    raise ContratoDesconhecido(
        f"Não encontrei a chave de {papel} na resposta do ADN.\n"
        f"  candidatos: {list(candidatos)}\n"
        f"  chaves reais: {sorted(dados)}\n"
        "Atualize app/adn/contrato.py com o nome real."
    )


def _opcional(dados: dict[str, Json], candidatos: tuple[str, ...]) -> Json:
    for c in candidatos:
        if c in dados:
            return dados[c]
    return None


def decodificar_conteudo(valor: str | bytes) -> bytes:
    """XML bruto a partir do campo de conteúdo.

    Detecção por conteúdo, não por nome de campo: base64 -> gzip -> texto.
    Isto não é chute sobre o contrato; é robustez sobre o payload.
    """
    if isinstance(valor, bytes):
        return valor
    try:
        bruto = base64.b64decode(valor, validate=True)
    except (binascii.Error, ValueError):
        return valor.encode()
    if bruto[:2] == b"\x1f\x8b":
        return gzip.decompress(bruto)
    if bruto.lstrip()[:1] in (b"<", b"\xef"):
        return bruto
    return valor.encode()


def _inteiro_obrigatorio(valor: Json, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int | str):
        raise ContratoDesconhecido(
            f"'{campo}' não é um inteiro: veio {type(valor).__name__}."
        )
    try:
        return int(valor)
    except ValueError:
        raise ContratoDesconhecido(f"'{campo}' não converte para inteiro.") from None


def extrair_lote(payload: dict[str, Json]) -> Lote:
    """Traduz a resposta crua do ADN para o nosso modelo."""
    chave_lote = _achar(payload, CANDIDATOS_LOTE, "lote de documentos")
    bruto = payload[chave_lote]
    if bruto is None:
        bruto = []
    if not isinstance(bruto, list):
        raise ContratoDesconhecido(
            f"'{chave_lote}' não é uma lista: veio {type(bruto).__name__}."
        )

    documentos: list[DocumentoDFe] = []
    for item in bruto:
        if not isinstance(item, dict):
            raise ContratoDesconhecido(
                f"item do lote não é objeto: veio {type(item).__name__}."
            )
        chave_nsu = _achar(item, CANDIDATOS_NSU_DOC, "NSU do documento")
        chave_conteudo = _achar(item, CANDIDATOS_CONTEUDO, "conteúdo XML")
        conteudo = item[chave_conteudo]
        if not isinstance(conteudo, str | bytes):
            raise ContratoDesconhecido(
                f"'{chave_conteudo}' não é texto: veio {type(conteudo).__name__}."
            )
        tipo = _opcional(item, CANDIDATOS_TIPO)
        documentos.append(
            DocumentoDFe(
                nsu=_inteiro_obrigatorio(item[chave_nsu], chave_nsu),
                xml=decodificar_conteudo(conteudo),
                tipo=str(tipo) if tipo is not None else None,
            )
        )

    def inteiro(valor: Json) -> int | None:
        if valor is None:
            return None
        return _inteiro_obrigatorio(valor, "NSU do lote")

    return Lote(
        documentos=tuple(documentos),
        max_nsu=inteiro(_opcional(payload, CANDIDATOS_MAX_NSU)),
        ult_nsu=inteiro(_opcional(payload, CANDIDATOS_ULT_NSU)),
    )
