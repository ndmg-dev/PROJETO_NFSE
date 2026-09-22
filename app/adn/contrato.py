"""O contrato do ADN — e o que dele ainda é desconhecido.

ESTADO: NÃO VERIFICADO CONTRA O ADN REAL.

O Manual dos Contribuintes v1.0 (12/02/2026) descreve a existência de
`GET /DFe/{NSU}` e `GET /NFSe/{chave}/Eventos` e nada mais: não fixa nomes de
campo da resposta, paginação, tamanho de lote, rate limit nem o código de fila
vazia. A spec §3.2 marca tudo isso como "a validar em homologação". O Swagger
da produção restrita exige certificado de cliente, então não há como ler o
contrato sem um .pfx.

Este módulo é a ÚNICA fronteira onde essas incógnitas moram. Tudo o mais no
sistema — loop de NSU, checkpoint, backoff, fila morta, detecção de lacuna —
é testado contra a forma declarada aqui e não muda quando os nomes reais
aparecerem.

COMO FECHAR ISTO
1. `python poc/fase0_dfe.py --ambiente restrita --pfx ... --dump-contrato`
2. substituir cada tupla de candidatos pelo nome único e verdadeiro
3. trocar `VERIFICADO = False` por `True` e rodar a suíte

Enquanto `VERIFICADO` for False, `Contrato.extrair_lote` aceita qualquer um
dos candidatos, mas NUNCA escolhe em silêncio: se nenhum casar, levanta
`ContratoDesconhecido` com as chaves reais que vieram.
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

CANDIDATOS_LOTE: Final[tuple[str, ...]] = ("loteDFe", "LoteDFe", "documentos", "DFe", "lote")
CANDIDATOS_NSU_DOC: Final[tuple[str, ...]] = ("NSU", "nsu")
CANDIDATOS_CONTEUDO: Final[tuple[str, ...]] = (
    "ArquivoXml", "arquivoXml", "XmlDFe", "xml", "documento",
)
CANDIDATOS_TIPO: Final[tuple[str, ...]] = (
    "TipoDocumento", "tipoDocumento", "tipo", "schema",
)
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
