"""Roda o pip direto de um arquivo .whl, sem instalar o pip antes.

O Python embutido do Windows não traz o pip. Em vez de baixar o get-pip.py (que muda a
cada versão e não dá para fixar por hash), o instalador baixa o .whl do pip de uma URL
fixa, confere o SHA-256 e o executa daqui: o .whl é um zip, e o Python importa módulos
de dentro dele.

    python -m app.local.rodar_pip caminho/pip-x.y.z-py3-none-any.whl install ...
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("uso: python -m app.local.rodar_pip pip.whl argumentos-do-pip...", file=sys.stderr)
        return 2
    sys.path.insert(0, argv[0])
    from pip._internal.cli.main import main as pip_main

    return int(pip_main(argv[1:]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
