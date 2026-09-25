"""Gera o instalador do agente para Windows: UM arquivo .bat com tudo dentro.

O contador baixa `Instalar-Agente-NFSe.bat` de /instalar e dá duplo clique. Nada
de zip para extrair, nada de comando, nada de instalar Java à mão.

A estrutura do arquivo está em app/instalador/empacotar.py. Aqui o script é a
biblioteca lib_windows.ps1 seguida de instalar_agente.ps1, e o pacote é o zip dos
fontes Java com o servidor.txt.

O pacote não leva segredo nenhum: só os fontes do spike (públicos, do próprio
repositório) e o endereço deste servidor.

    python -m app.instalador.agente --url http://servidor:8000 --saida Instalar.bat
"""

from __future__ import annotations

import argparse
import io
import re
import zipfile
from pathlib import Path
from typing import Final

from app.instalador.empacotar import MARCADOR_PAYLOAD, MARCADOR_PS1, montar_bat

RAIZ: Final = Path(__file__).resolve().parents[2]
FONTES_PADRAO: Final = RAIZ / "agente" / "spike"
SCRIPT_PADRAO: Final = Path(__file__).with_name("instalar_agente.ps1")

BIBLIOTECA_PADRAO: Final = Path(__file__).with_name("lib_windows.ps1")

ARQUIVOS_JAVA: Final = (
    "Nucleo.java",
    "CadastroEmpresa.java",
    "ProvarHandshakeMTLS.java",
    "ProvarHandshakeMTLSGui.java",
)

_URL_SEGURA: Final = re.compile(r"^https?://[A-Za-z0-9._\-]+(:\d{1,5})?$")

LEIAME: Final = """Ferramenta de teste de certificado NFS-e (versão de validação).

Verifica se o certificado A1 já instalado neste computador pode ser usado para
autenticar uma conexão, SEM exportá-lo. Não envia nada para lugar nenhum.

O agente completo, que sincroniza as notas, ainda não existe: quando existir,
será instalado pelo mesmo link.
"""


def url_servidor_segura(url: str) -> str:
    """Só aceita http(s)://host[:porta]. O valor vem do cabeçalho Host da
    requisição, que quem chama controla: entra em servidor.txt e em mais nada."""
    limpa = url.strip().rstrip("/")
    return limpa if _URL_SEGURA.match(limpa) else ""


def montar_pacote(url_servidor: str, pasta_fontes: Path = FONTES_PADRAO) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in ARQUIVOS_JAVA:
            z.write(pasta_fontes / nome, nome)
        z.writestr("servidor.txt", url_servidor_segura(url_servidor) + "\n")
        z.writestr("LEIAME.txt", LEIAME)
    return buffer.getvalue()


def gerar_instalador(
    url_servidor: str,
    *,
    pasta_fontes: Path = FONTES_PADRAO,
    script: Path = SCRIPT_PADRAO,
    biblioteca: Path = BIBLIOTECA_PADRAO,
) -> bytes:
    # A biblioteca compartilhada vem ANTES do script: as funções de download com
    # verificação de integridade existem num lugar só, para os dois instaladores.
    texto = (
        biblioteca.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        + "\n"
        + script.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    )
    return montar_bat(
        "Instalando a ferramenta de teste de certificado NFS-e",
        texto,
        montar_pacote(url_servidor, pasta_fontes),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera o instalador do agente para Windows.")
    ap.add_argument("--url", default="", help="endereço deste servidor (vai em servidor.txt)")
    ap.add_argument("--saida", default="Instalar-Agente-NFSe.bat", type=Path)
    args = ap.parse_args()
    args.saida.write_bytes(gerar_instalador(args.url))
    print(f"gerado: {args.saida}")


if __name__ == "__main__":
    main()

__all__ = [
    "ARQUIVOS_JAVA",
    "MARCADOR_PAYLOAD",
    "MARCADOR_PS1",
    "gerar_instalador",
    "montar_pacote",
    "url_servidor_segura",
]
