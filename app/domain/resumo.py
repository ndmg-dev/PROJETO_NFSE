"""Aba `Resumo` do relatório (spec §5.1).

Agregado por situação, em `Decimal`. É aqui que o relatório fecha em
198.227,91 em vez do 198227.90999999997 que o portal imprime.

Módulo de domínio puro: sem I/O, sem ORM, sem rede. Recebe linhas e devolve
números.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from app.core.dinheiro import somar
from app.domain.layout_relacao import SITUACOES

TOTAL: Final = "Total"


class LinhaResumivel(Protocol):
    """O mínimo que o resumo precisa de uma nota.

    Protocol em vez do modelo do ORM: o cálculo fica testável sem banco e não
    trava numa classe do SQLAlchemy.
    """

    @property
    def situacao(self) -> str: ...

    @property
    def valor_servico(self) -> Decimal | None: ...


@dataclass(frozen=True)
class LinhaResumo:
    situacao: str
    quantidade: int
    valor: Decimal


@dataclass(frozen=True)
class Resumo:
    linhas: tuple[LinhaResumo, ...]
    total: LinhaResumo

    def por_situacao(self, situacao: str) -> LinhaResumo:
        for linha in self.linhas:
            if linha.situacao == situacao:
                return linha
        raise KeyError(situacao)


def calcular_resumo(
    notas: Iterable[LinhaResumivel],
    situacoes: Sequence[str] = SITUACOES,
) -> Resumo:
    """Agrega por situação, sempre nas três situações do portal.

    Situação com zero notas aparece com 0 — o portal também emite a linha, e
    omiti-la faria o relatório parecer incompleto.

    Nota sem `valor_servico` conta na quantidade mas soma zero: a nota existe,
    o valor é que não foi extraído. Descartá-la esconderia a lacuna.
    """
    materializadas = list(notas)
    desconhecidas = {n.situacao for n in materializadas} - set(situacoes)
    if desconhecidas:
        raise ValueError(
            f"situação fora do layout do portal: {sorted(desconhecidas)}. "
            "Acrescente à tupla SITUACOES antes de gerar o relatório."
        )

    linhas: list[LinhaResumo] = []
    for situacao in situacoes:
        do_grupo = [n for n in materializadas if n.situacao == situacao]
        linhas.append(
            LinhaResumo(
                situacao=situacao,
                quantidade=len(do_grupo),
                valor=somar(
                    n.valor_servico for n in do_grupo if n.valor_servico is not None
                ),
            )
        )

    return Resumo(
        linhas=tuple(linhas),
        total=LinhaResumo(
            situacao=TOTAL,
            quantidade=len(materializadas),
            valor=somar(linha.valor for linha in linhas),
        ),
    )
