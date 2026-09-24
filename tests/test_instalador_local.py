"""O pacote do instalador local: o que entra, o que NUNCA pode entrar."""

from __future__ import annotations

import base64
import io
import zipfile

from app.instalador import local
from app.instalador.empacotar import MARCADOR_PAYLOAD


def _pacote() -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(local.montar_pacote()))


def test_pacote_tem_codigo_scripts_e_agente() -> None:
    nomes = set(_pacote().namelist())
    assert "codigo/app/api/main.py" in nomes
    assert "codigo/alembic.ini" in nomes
    assert "codigo/requirements-local.lock" in nomes
    for s in local.SCRIPTS_DE_USO:
        assert f"bin/{s}" in nomes
    assert {"bin/lib_windows.ps1", "bin/comum_nfse.ps1"} <= nomes
    assert "agente/Nucleo.java" in nomes


def test_pacote_nao_leva_segredo_nem_dado_de_cliente() -> None:
    for nome in _pacote().namelist():
        baixo = nome.lower()
        assert not baixo.endswith((".pdf", ".pfx", ".p12", ".xlsx", ".pyc")), nome
        assert not baixo.startswith(("codigo/tests", "codigo/poc", "codigo/referencia")), nome
        assert "/.env" not in baixo and ".git" not in baixo.split("/"), nome


def test_bat_gerado_decodifica_para_o_mesmo_pacote(tmp_path) -> None:  # type: ignore[no-untyped-def]
    saida = tmp_path / "i.bat"
    local.gerar(saida)
    texto = saida.read_bytes().decode("utf-8")
    assert "\r\n" in texto and not texto.startswith("﻿")
    b64 = texto.rsplit(MARCADOR_PAYLOAD, 1)[1]
    assert zipfile.ZipFile(io.BytesIO(base64.b64decode(b64))).testzip() is None
    # o script embutido traz as três partes, na ordem em que uma depende da outra
    i_lib = texto.index("function Extrair-Payload")
    i_comum = texto.index("function Caminhos-Nfse")
    i_main = texto.index("function Principal")
    assert i_lib < i_comum < i_main
