"""Extrai o .txz do PostgreSQL usando só a biblioteca padrão do Python.

O pacote do PostgreSQL (Zonky) vem como um .txz dentro de um .jar. O Windows PowerShell
5.1 não lê .txz, e depender do tar.exe do Windows (que precisa de suporte a xz) seria
apostar; o Python embutido já está instalado e tem `tarfile` e `lzma`.

Fica em um módulo, e não num `python -c "..."` dentro do PowerShell, porque o 5.1 estraga
aspas duplas ao passar argumentos a programas externos.

    python -m app.local.extrair_txz arquivo.txz pasta-destino
"""

from __future__ import annotations

import sys
import tarfile
from pathlib import Path


def extrair(txz: Path, destino: Path) -> int:
    """Devolve quantos arquivos extraiu. filter='data' recusa caminho fora do destino,
    link perigoso e permissão estranha: o conteúdo vem de fora."""
    destino.mkdir(parents=True, exist_ok=True)
    with tarfile.open(txz, "r:xz") as t:
        membros = t.getmembers()
        t.extractall(destino, members=membros, filter="data")
    return sum(1 for m in membros if m.isfile())


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("uso: python -m app.local.extrair_txz arquivo.txz destino", file=sys.stderr)
        return 2
    print(f"{extrair(Path(argv[0]), Path(argv[1]))} arquivos")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
