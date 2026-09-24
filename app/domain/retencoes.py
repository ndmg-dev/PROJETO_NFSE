"""Linhas e totais do relatório de Retenções e Divergências de líquido (spec §5.2).

Junta o que a nota destaca (IRRF, contribuições, ISSQN retido, PIS e COFINS) com
a análise de app/domain/liquido.py, que recalcula o líquido esperado em dois
cenários e o compara com o declarado.

PIS e COFINS ficam SEPARADOS dos totais de retenção. O DANFSe os rotula "Débito
Apuração Própria" (tributo do próprio prestador), não "Retidos". Somá-los ao
total retido decidiria em silêncio a discussão fiscal; aqui aparecem à parte, e
quem escritura decide.

Módulo de domínio puro: sem I/O, sem ORM, sem rede.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.core.dinheiro import somar
from app.domain.liquido import (
    AnaliseLiquido,
    NotaParaLiquido,
    Situacao,
    analisar_liquido,
)

ROTULO_DA_ANALISE: dict[Situacao, str] = {
    "consistente": "Consistente",
    "retencao_nao_abatida": "Retenção destacada e não abatida do líquido",
    "liquido_acima_do_bruto": "Líquido acima do valor do serviço",
    "liquido_abaixo_do_esperado": "Líquido abaixo do esperado",
    "indeterminado": "Indeterminado (falta dado na nota)",
}


class NotaParaRelatorio(NotaParaLiquido, Protocol):
    @property
    def chave_acesso(self) -> str: ...
    @property
    def numero(self) -> str | None: ...
    @property
    def data_geracao(self) -> datetime | None: ...
    @property
    def competencia(self) -> date | None: ...
    @property
    def papel(self) -> str: ...
    @property
    def situacao(self) -> str: ...
    @property
    def prestador_cnpj(self) -> str | None: ...
    @property
    def prestador_nome(self) -> str | None: ...
    @property
    def tomador_cnpj(self) -> str | None: ...
    @property
    def tomador_nome(self) -> str | None: ...


@dataclass(frozen=True)
class LinhaRetencao:
    chave_acesso: str
    numero: str | None
    data_geracao: datetime | None
    competencia: date | None
    papel: str
    situacao_nota: str
    prestador_cnpj: str | None
    prestador_nome: str | None
    tomador_cnpj: str | None
    tomador_nome: str | None
    valor_servico: Decimal | None
    irrf: Decimal | None
    contrib_sociais_retidas: Decimal | None
    contrib_previd_retida: Decimal | None
    issqn_retido: Decimal | None  # só quando a nota o marca como retido
    pis_debito: Decimal | None
    cofins_debito: Decimal | None
    analise: AnaliseLiquido


@dataclass(frozen=True)
class TotaisRetencoes:
    notas: int
    com_atencao: int
    por_analise: dict[Situacao, int]
    valor_servico: Decimal
    irrf: Decimal
    contrib_sociais_retidas: Decimal
    contrib_previd_retida: Decimal
    issqn_retido: Decimal
    retencoes_estritas: Decimal
    pis_debito: Decimal
    cofins_debito: Decimal
    # Quanto de retenção destacada não foi abatido do líquido, por cenário. Só
    # das notas em `retencao_nao_abatida`: é o tamanho do problema do áudio.
    nao_abatido_estrito: Decimal
    nao_abatido_ampliado: Decimal


def montar_linha(nota: NotaParaRelatorio) -> LinhaRetencao:
    return LinhaRetencao(
        chave_acesso=nota.chave_acesso,
        numero=nota.numero,
        data_geracao=nota.data_geracao,
        competencia=nota.competencia,
        papel=nota.papel,
        situacao_nota=nota.situacao,
        prestador_cnpj=nota.prestador_cnpj,
        prestador_nome=nota.prestador_nome,
        tomador_cnpj=nota.tomador_cnpj,
        tomador_nome=nota.tomador_nome,
        valor_servico=nota.valor_servico,
        irrf=nota.irrf,
        contrib_sociais_retidas=nota.contrib_sociais_retidas,
        contrib_previd_retida=nota.contrib_previd_retida,
        issqn_retido=nota.valor_issqn if nota.issqn_retido is True else None,
        pis_debito=nota.pis_debito,
        cofins_debito=nota.cofins_debito,
        analise=analisar_liquido(nota),
    )


def montar_linhas(
    notas: Iterable[NotaParaRelatorio], *, somente_divergentes: bool = False
) -> list[LinhaRetencao]:
    """Uma linha por nota, as que pedem atenção primeiro; depois, as mais novas.

    `somente_divergentes` filtra pela análise, por isso mora aqui e não na
    consulta SQL: a divergência é calculada, não guardada.
    """
    linhas = [montar_linha(n) for n in notas]
    if somente_divergentes:
        linhas = [linha for linha in linhas if linha.analise.requer_atencao]
    return sorted(
        linhas,
        key=lambda x: (
            not x.analise.requer_atencao,
            -(x.data_geracao.timestamp() if x.data_geracao else 0.0),
        ),
    )


def _soma(valores: Iterable[Decimal | None]) -> Decimal:
    return somar(v for v in valores if v is not None)


def totalizar(linhas: Iterable[LinhaRetencao]) -> TotaisRetencoes:
    itens = list(linhas)
    por_analise: dict[Situacao, int] = {rotulo: 0 for rotulo in ROTULO_DA_ANALISE}
    for linha in itens:
        por_analise[linha.analise.situacao] += 1

    nao_abatidas = [i for i in itens if i.analise.situacao == "retencao_nao_abatida"]
    return TotaisRetencoes(
        notas=len(itens),
        com_atencao=sum(1 for i in itens if i.analise.requer_atencao),
        por_analise=por_analise,
        valor_servico=_soma(i.valor_servico for i in itens),
        irrf=_soma(i.irrf for i in itens),
        contrib_sociais_retidas=_soma(i.contrib_sociais_retidas for i in itens),
        contrib_previd_retida=_soma(i.contrib_previd_retida for i in itens),
        issqn_retido=_soma(i.issqn_retido for i in itens),
        retencoes_estritas=somar(i.analise.retencoes_estritas for i in itens),
        pis_debito=_soma(i.pis_debito for i in itens),
        cofins_debito=_soma(i.cofins_debito for i in itens),
        nao_abatido_estrito=_soma(i.analise.diferenca_estrita for i in nao_abatidas),
        nao_abatido_ampliado=_soma(i.analise.diferenca_ampliada for i in nao_abatidas),
    )
