"""Gera o instalador do agente para Windows: UM arquivo .bat com tudo dentro.

O contador baixa `Instalar-Agente-NFSe.bat` de /instalar e dá duplo clique. Nada
de zip para extrair, nada de comando, nada de instalar Java à mão.

Estrutura do arquivo (linhas em CRLF; o cmd falha com LF):

    @echo off ... powershell -Command "<extrai o script depois de #PS1# e o executa>"
    exit /b
    #PS1#
    <instalar_agente.ps1>
    #PAYLOAD#
    <zip dos fontes Java + servidor.txt, em base64>

O cmd nunca lê nada depois de `exit /b`, então o script e o pacote podem ficar
ali, com acentos e tudo. Os marcadores são montados por concatenação na linha de
comando ('#'+'PS1#') para o texto literal aparecer UMA vez, no lugar certo.

O pacote não leva segredo nenhum: só os fontes do spike (públicos, do próprio
repositório) e o endereço deste servidor.

    python -m app.instalador.agente --url http://servidor:8000 --saida Instalar.bat
"""

from __future__ import annotations

import argparse
import base64
import io
import re
import zipfile
from pathlib import Path
from typing import Final

RAIZ: Final = Path(__file__).resolve().parents[2]
FONTES_PADRAO: Final = RAIZ / "agente" / "spike"
SCRIPT_PADRAO: Final = Path(__file__).with_name("instalar_agente.ps1")

ARQUIVOS_JAVA: Final = ("Nucleo.java", "ProvarHandshakeMTLS.java", "ProvarHandshakeMTLSGui.java")
MARCADOR_PS1: Final = "#PS1#"
MARCADOR_PAYLOAD: Final = "#PAYLOAD#"

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
) -> bytes:
    corpo_ps1 = script.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    for marcador in (MARCADOR_PS1, MARCADOR_PAYLOAD):
        if marcador in corpo_ps1:
            raise ValueError(f"o script não pode conter o marcador {marcador}")

    pacote = base64.b64encode(montar_pacote(url_servidor, pasta_fontes)).decode("ascii")
    linhas_pacote = [pacote[i : i + 76] for i in range(0, len(pacote), 76)]

    cabecalho = [
        "@echo off",
        "chcp 65001 >nul",
        "title Instalando a ferramenta de teste de certificado NFS-e",
        'set "NFSE_INSTALADOR=%~f0"',
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "'
        "$t=[IO.File]::ReadAllText($env:NFSE_INSTALADOR,[Text.Encoding]::UTF8); "
        "$m='#'+'PS1#'; "
        'Invoke-Expression $t.Substring($t.LastIndexOf($m)+$m.Length)"',
        "echo.",
        "pause",
        "exit /b",
        MARCADOR_PS1,
    ]
    texto = "\r\n".join(
        [*cabecalho, *corpo_ps1.split("\n"), MARCADOR_PAYLOAD, *linhas_pacote, ""]
    )
    # UTF-8 SEM BOM: o cmd tropeça num BOM e a primeira linha vira lixo.
    return texto.encode("utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera o instalador do agente para Windows.")
    ap.add_argument("--url", default="", help="endereço deste servidor (vai em servidor.txt)")
    ap.add_argument("--saida", default="Instalar-Agente-NFSe.bat", type=Path)
    args = ap.parse_args()
    args.saida.write_bytes(gerar_instalador(args.url))
    print(f"gerado: {args.saida}")


if __name__ == "__main__":
    main()
