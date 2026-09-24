"""Gera o instalador local (sem Docker) para Windows: UM arquivo .bat com tudo dentro.

Diferente do instalador do agente, este leva a APLICAÇÃO inteira no pacote (código,
migrations, lock de dependências, scripts de uso diário e fontes do teste de
certificado). O que é grande (Python, PostgreSQL, JDK) é baixado na instalação, com
SHA-256 conferido contra app/instalador/pins.json.

Estrutura do pacote (zip dentro do .bat): codigo/, bin/, agente/. Nenhum segredo entra:
as senhas são geradas na máquina do contador, na primeira instalação.

    python -m app.instalador.local --saida Instalar-NFSe.bat
"""

from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path
from typing import Final

from app.instalador.agente import ARQUIVOS_JAVA, BIBLIOTECA_PADRAO, FONTES_PADRAO, RAIZ
from app.instalador.empacotar import MARCADOR_PAYLOAD, MARCADOR_PS1, montar_bat

PASTA_PS: Final = Path(__file__).with_name("windows")
COMUM: Final = PASTA_PS / "comum_nfse.ps1"
SCRIPT_PRINCIPAL: Final = PASTA_PS / "instalar_nfse.ps1"
SCRIPTS_DE_USO: Final = (
    "Abrir-NFSe.ps1",
    "Parar-NFSe.ps1",
    "Copia-de-seguranca.ps1",
    "Restaurar-copia.ps1",
    "Desinstalar-NFSe.ps1",
)
ARQUIVOS_RAIZ: Final = (
    "alembic.ini",
    "requirements-local.txt",
    "requirements-local.lock",
)
# Só o necessário para rodar; testes, poc, referências (PDFs de clientes) ficam de fora.
PASTAS_DE_CODIGO: Final = ("app", "alembic")
IGNORAR: Final = ("__pycache__", ".pyc", ".pytest_cache", ".mypy_cache")


def _ignorado(caminho: Path) -> bool:
    return any(p in str(caminho) for p in IGNORAR)


def montar_pacote(raiz: Path = RAIZ) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for pasta in PASTAS_DE_CODIGO:
            for arq in sorted((raiz / pasta).rglob("*")):
                if arq.is_file() and not _ignorado(arq):
                    z.write(arq, f"codigo/{arq.relative_to(raiz).as_posix()}")
        for nome in ARQUIVOS_RAIZ:
            z.write(raiz / nome, f"codigo/{nome}")
        for nome in SCRIPTS_DE_USO:
            z.write(PASTA_PS / nome, f"bin/{nome}")
        # Os scripts de uso carregam as bibliotecas do lado deles.
        z.write(BIBLIOTECA_PADRAO, "bin/lib_windows.ps1")
        z.write(COMUM, "bin/comum_nfse.ps1")
        for nome in ARQUIVOS_JAVA:
            z.write(FONTES_PADRAO / nome, f"agente/{nome}")
    return buffer.getvalue()


def montar_script() -> str:
    partes = [BIBLIOTECA_PADRAO, COMUM, SCRIPT_PRINCIPAL]
    return "\n".join(p.read_text(encoding="utf-8") for p in partes)


def gerar(saida: Path, raiz: Path = RAIZ) -> None:
    bat = montar_bat("Instalar NFS-e", montar_script(), montar_pacote(raiz))
    saida.write_bytes(bat)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()
    gerar(args.saida)
    print(f"gerado: {args.saida} ({args.saida.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

__all__ = ["MARCADOR_PAYLOAD", "MARCADOR_PS1", "gerar", "montar_pacote", "montar_script"]
