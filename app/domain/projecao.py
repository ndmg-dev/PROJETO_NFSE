"""Decide o que fazer com um documento já interpretado (spec §7).

Recebe o DTO do parser e o CNPJ da empresa cuja fila trouxe o documento; devolve
ou o que gravar, ou uma rejeição com o motivo. Não sabe de banco, arquivo nem
rede — a persistência mora em app/workers/projecao.py.

Regra de fundo: rejeitar é melhor que gravar palpite. Nota sem valor, sem chave
ou de papel indeterminado não vira linha em `nfse`; vira documento em erro, com
o XML bruto preservado, e aparece na fila de revisão em vez de sumir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final, Literal

from app.domain.parser import EventoDTO, NFSeDTO

Papel = Literal["prestador", "tomador"]

# HIPÓTESE — código do evento -> situação resultante da nota. Vem de memória do
# padrão nacional (101101 cancelamento; 105102 cancelamento por substituição) e
# NÃO foi confrontada com o manual nem com um evento real. Código fora desta
# tabela não altera a situação: o evento é gravado e a nota fica como estava.
# Uma situação errada aqui é pior que uma ausente (nota válida aparecendo como
# cancelada), então a tabela só cresce com confirmação.
SITUACAO_POR_TIPO_EVENTO: Final[dict[str, str]] = {
    "101101": "Cancelada",
    "105102": "Substituída",
}


@dataclass(frozen=True)
class NotaProjetavel:
    papel: Papel
    dto: NFSeDTO  # com CNPJ/CPF já normalizados para dígitos
    avisos: tuple[str, ...]


@dataclass(frozen=True)
class EventoProjetavel:
    chave_acesso: str
    tipo_evento: str
    data_evento: datetime | None
    autor: str | None
    motivo: str | None
    nova_situacao: str | None


@dataclass(frozen=True)
class Rejeicao:
    motivo: str


def _digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def _documento_normalizado(texto: str | None, quem: str) -> tuple[str | None, str | None]:
    """CPF (11) ou CNPJ (14) só com dígitos; senão None e um aviso.

    Nunca trunca: nfse.*_cnpj é String(14), e um documento de outro formato
    (NIF de tomador estrangeiro, por exemplo) não pode derrubar a nota inteira.
    """
    d = _digitos(texto)
    if not d:
        return None, None
    if len(d) in (11, 14):
        return d, None
    return None, f"{quem}: documento com {len(d)} dígitos, não gravado"


def resolver_papel(dto: NFSeDTO, cnpj_empresa: str) -> Papel | None:
    """A empresa é tomadora ou prestadora desta nota?

    Se o mesmo CNPJ aparecer nos dois lados (raro), vale tomador — o mesmo
    critério de NFSeDTO.papel_de. Nenhum dos dois: None, e quem chama decide.
    """
    alvo = _digitos(cnpj_empresa)
    if not alvo:
        return None
    if _digitos(dto.tomador_cnpj) == alvo:
        return "tomador"
    if _digitos(dto.prestador_cnpj) == alvo:
        return "prestador"
    return None


def decidir_projecao(dto: NFSeDTO, cnpj_empresa: str) -> NotaProjetavel | Rejeicao:
    if dto.chave_acesso is None:
        return Rejeicao("XML sem chave de acesso de 50 dígitos")

    if dto.valor_servico is None:
        detalhe = ", ".join(dto.campos_ausentes) or "campo não encontrado"
        return Rejeicao(f"XML sem valor do serviço legível ({detalhe})")

    papel = resolver_papel(dto, cnpj_empresa)
    if papel is None:
        return Rejeicao(
            "o CNPJ da empresa não é prestador nem tomador desta nota (possível "
            "intermediário); papel indeterminado, nada foi gravado em nfse"
        )

    prestador, aviso_prestador = _documento_normalizado(dto.prestador_cnpj, "prestador")
    tomador, aviso_tomador = _documento_normalizado(dto.tomador_cnpj, "tomador")
    avisos = tuple(a for a in (aviso_prestador, aviso_tomador) if a is not None)

    return NotaProjetavel(
        papel=papel,
        dto=replace(dto, prestador_cnpj=prestador, tomador_cnpj=tomador),
        avisos=avisos,
    )


def decidir_evento(dto: EventoDTO) -> EventoProjetavel | Rejeicao:
    if dto.chave_acesso is None:
        return Rejeicao("evento sem a chave de acesso da nota")
    if dto.tipo_evento is None:
        return Rejeicao("evento sem tipo")
    return EventoProjetavel(
        chave_acesso=dto.chave_acesso,
        tipo_evento=dto.tipo_evento,
        data_evento=dto.data_evento,
        autor=dto.autor,
        motivo=dto.motivo,
        nova_situacao=SITUACAO_POR_TIPO_EVENTO.get(dto.tipo_evento),
    )
