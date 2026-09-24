"""Limite de tentativas erradas do código de configuração.

40 bits não caem em força bruta com um limite razoável: 5 erros por janela por
origem, e um teto global para quem distribui as tentativas. Em memória, por
processo: suficiente para uma janela que só existe até o primeiro acesso.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable


class LimitadorDeTentativas:
    def __init__(
        self,
        maximo: int,
        janela_s: float,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._maximo = maximo
        self._janela = janela_s
        self._relogio = relogio
        self._falhas: defaultdict[str, deque[float]] = defaultdict(deque)

    def _podar(self, chave: str) -> deque[float]:
        fila = self._falhas[chave]
        limite = self._relogio() - self._janela
        while fila and fila[0] <= limite:
            fila.popleft()
        return fila

    def bloqueado(self, chave: str) -> bool:
        return len(self._podar(chave)) >= self._maximo

    def registrar_falha(self, chave: str) -> None:
        self._podar(chave).append(self._relogio())

    def limpar_tudo(self) -> None:
        self._falhas.clear()
