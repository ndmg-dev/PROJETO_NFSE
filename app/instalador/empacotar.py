"""Monta um instalador de Windows em UM arquivo .bat, com tudo dentro.

Estrutura do arquivo (linhas em CRLF; o cmd falha com LF):

    @echo off ... powershell -Command "<extrai o script depois de #PS1# e o executa>"
    exit /b
    #PS1#
    <script PowerShell>
    #PAYLOAD#
    <zip do pacote, em base64>

O cmd nunca lê nada depois de `exit /b`, então o script e o pacote podem ficar ali,
com acentos e tudo. Os marcadores são montados por concatenação na linha de comando
('#'+'PS1#') para o texto literal aparecer UMA vez, no lugar certo.
"""

from __future__ import annotations

import base64
from typing import Final

MARCADOR_PS1: Final = "#PS1#"
MARCADOR_PAYLOAD: Final = "#PAYLOAD#"


def montar_bat(titulo: str, script: str, pacote: bytes) -> bytes:
    if not titulo.isascii():
        raise ValueError("o título do .bat é lido pelo cmd: só ASCII")
    corpo = script.replace("\r\n", "\n")
    for marcador in (MARCADOR_PS1, MARCADOR_PAYLOAD):
        if marcador in corpo:
            raise ValueError(f"o script não pode conter o marcador {marcador}")

    codificado = base64.b64encode(pacote).decode("ascii")
    linhas_pacote = [codificado[i : i + 76] for i in range(0, len(codificado), 76)]
    cabecalho = [
        "@echo off",
        "chcp 65001 >nul",
        f"title {titulo}",
        'set "NFSE_INSTALADOR=%~f0"',
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "'
        "$t=[IO.File]::ReadAllText($env:NFSE_INSTALADOR,[Text.Encoding]::UTF8); "
        "$m='#'+'PS1#'; $f='#'+'PAYLOAD#'; "
        "$i=$t.LastIndexOf($m)+$m.Length; "
        # só o script: o pacote em base64 vem depois de #PAYLOAD# e NÃO é PowerShell
        'Invoke-Expression $t.Substring($i,$t.LastIndexOf($f)-$i)"',
        "echo.",
        "pause",
        "exit /b",
        MARCADOR_PS1,
    ]
    texto = "\r\n".join([*cabecalho, *corpo.split("\n"), MARCADOR_PAYLOAD, *linhas_pacote, ""])
    # UTF-8 SEM BOM: o cmd tropeça num BOM e a primeira linha vira lixo.
    return texto.encode("utf-8")
