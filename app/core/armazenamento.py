"""Guarda do XML bruto — a fonte da verdade do sistema (spec §7).

O XML nunca é sobrescrito nem apagado: o banco relacional é projeção
reconstruível, o arquivo não. Guarda fiscal de 5 anos, na prática 10.

Backend local no MVP. Trocar por S3/GCS é implementar `Armazenamento`.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path


class Armazenamento(ABC):
    @abstractmethod
    def guardar(self, chave: str, conteudo: bytes) -> str: ...

    @abstractmethod
    def ler(self, caminho: str) -> bytes: ...


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


class ArmazenamentoLocal(Armazenamento):
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz

    def guardar(self, chave: str, conteudo: bytes) -> str:
        destino = self.raiz / chave
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            # Idempotência: reprocessar um lote reencontra o mesmo arquivo.
            # Conteúdo diferente na mesma chave é corrupção, não repetição.
            if sha256(destino.read_bytes()) != sha256(conteudo):
                raise ValueError(
                    f"conteúdo divergente para a chave já gravada: {chave}"
                )
            return str(destino)
        provisorio = destino.with_suffix(destino.suffix + ".parcial")
        provisorio.write_bytes(conteudo)
        provisorio.rename(destino)  # rename é atômico: nunca fica meio escrito
        return str(destino)

    def ler(self, caminho: str) -> bytes:
        return Path(caminho).read_bytes()
