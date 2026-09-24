"""Página /instalar e o instalador do agente para Windows.

O que o instalador FAZ no Windows (extrair, achar Java, compilar) é testado em
PowerShell: make test-windows. Aqui: o que o servidor entrega e o que não pode
haver nele.
"""

from __future__ import annotations

import base64
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import obter_config
from app.instalador.agente import (
    ARQUIVOS_JAVA,
    MARCADOR_PAYLOAD,
    MARCADOR_PS1,
    gerar_instalador,
    montar_pacote,
    url_servidor_segura,
)

RAIZ = Path(__file__).resolve().parents[1]
URL = "/instalar/Instalar-Agente-NFSe.bat"


def pacote_do(corpo: bytes) -> zipfile.ZipFile:
    texto = corpo.decode("utf-8")
    base64_do_pacote = texto.split(MARCADOR_PAYLOAD + "\r\n", 1)[1]
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(base64_do_pacote)))


# =============================================================== a página ===


def test_pagina_de_instalacao_e_servida(cliente: TestClient) -> None:
    r = cliente.get("/instalar")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert URL in r.text, "a página precisa apontar para o instalador"


def test_pagina_de_instalacao_nao_exige_login(cliente: TestClient) -> None:
    """Quem abre o link numa estação ainda não tem conta."""
    assert cliente.get("/instalar").status_code == 200
    assert cliente.get(URL).status_code == 200


# ============================================================ o download ===


def test_download_tem_cabecalhos_de_arquivo(cliente: TestClient) -> None:
    r = cliente.get(URL)
    assert r.status_code == 200
    assert 'attachment; filename="Instalar-Agente-NFSe.bat"' in r.headers["content-disposition"]
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"


def test_formato_do_bat_que_o_cmd_aceita(cliente: TestClient) -> None:
    corpo = cliente.get(URL).content
    assert not corpo.startswith(b"\xef\xbb\xbf"), "BOM quebra a primeira linha no cmd"
    assert corpo.startswith(b"@echo off\r\n")
    texto = corpo.decode("utf-8")
    assert "\n" not in texto.replace("\r\n", ""), "LF solto: o cmd falha"
    cabecalho = texto.split(MARCADOR_PS1 + "\r\n", 1)[0].encode("utf-8")
    assert all(b < 128 for b in cabecalho), "o cmd interpreta o cabeçalho: só ASCII"
    assert "exit /b" in texto.split(MARCADOR_PS1)[0]


def test_marcadores_aparecem_uma_vez_como_linha_inteira(cliente: TestClient) -> None:
    linhas = cliente.get(URL).content.decode("utf-8").split("\r\n")
    assert linhas.count(MARCADOR_PS1) == 1
    assert linhas.count(MARCADOR_PAYLOAD) == 1
    assert linhas.index(MARCADOR_PS1) < linhas.index(MARCADOR_PAYLOAD)


def test_pacote_tem_exatamente_o_esperado(cliente: TestClient) -> None:
    z = pacote_do(cliente.get(URL).content)
    assert sorted(z.namelist()) == sorted([*ARQUIVOS_JAVA, "servidor.txt", "LEIAME.txt"])


def test_fontes_java_sao_identicos_aos_do_repositorio(cliente: TestClient) -> None:
    z = pacote_do(cliente.get(URL).content)
    for nome in ARQUIVOS_JAVA:
        assert z.read(nome) == (RAIZ / "agente" / "spike" / nome).read_bytes(), nome


def test_servidor_txt_traz_o_endereco_de_quem_baixou(cliente: TestClient) -> None:
    z = pacote_do(cliente.get(URL).content)
    assert z.read("servidor.txt").decode().strip() == "http://testserver"


def test_o_script_embutido_e_o_do_repositorio(cliente: TestClient) -> None:
    texto = cliente.get(URL).content.decode("utf-8")
    embutido = texto.split(MARCADOR_PS1 + "\r\n", 1)[1].split(MARCADOR_PAYLOAD, 1)[0]
    pasta = RAIZ / "app" / "instalador"
    fonte = (pasta / "lib_windows.ps1").read_text(encoding="utf-8") + "\n" + (
        pasta / "instalar_agente.ps1"
    ).read_text(encoding="utf-8")
    assert embutido.replace("\r\n", "\n").strip() == fonte.replace("\r\n", "\n").strip()


# ==================================================== o que NÃO pode haver ===


def test_nenhum_segredo_do_servidor_no_arquivo(cliente: TestClient) -> None:
    corpo = cliente.get(URL).content
    texto = corpo.decode("utf-8", errors="ignore")
    assert obter_config().jwt_secret.get_secret_value() not in texto
    assert obter_config().database_url not in texto
    z = pacote_do(corpo)
    todo_o_pacote = b"".join(z.read(n) for n in z.namelist()).decode("utf-8", errors="ignore")
    assert obter_config().jwt_secret.get_secret_value() not in todo_o_pacote
    assert not any(n.endswith((".env", ".pfx", ".p12", ".pem", ".key")) for n in z.namelist())


def test_tamanho_razoavel(cliente: TestClient) -> None:
    assert 5_000 < len(cliente.get(URL).content) < 200_000


def test_host_malicioso_nao_chega_ao_arquivo(cliente: TestClient) -> None:
    """O cabeçalho Host é de quem chama; só vale se tiver a forma de um endereço."""
    r = cliente.get(URL, headers={"Host": "evil.com/x"})
    assert pacote_do(r.content).read("servidor.txt").decode().strip() == ""


# ============================================================ o gerador ===


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("http://10.0.0.106:8000", "http://10.0.0.106:8000"),
        ("http://10.0.0.106:8000/", "http://10.0.0.106:8000"),
        ("https://nfse.exemplo.com.br", "https://nfse.exemplo.com.br"),
        ("http://servidor", "http://servidor"),
        ("  http://a.b:80  ", "http://a.b:80"),
        ("", ""),
        ("javascript:alert(1)", ""),
        ("http://a b", ""),
        ("http://evil.com/x", ""),
        ("http://evil.com\"; calc", ""),
        ("ftp://servidor", ""),
        ("http://user:pass@servidor", ""),
    ],
)
def test_url_do_servidor_so_aceita_http_host_porta(entrada: str, esperado: str) -> None:
    assert url_servidor_segura(entrada) == esperado


def test_script_com_marcador_e_recusado(tmp_path: Path) -> None:
    """Um marcador dentro do script confundiria a extração no Windows."""
    ruim = tmp_path / "ruim.ps1"
    ruim.write_text(f"Write-Host 'oi'\n{MARCADOR_PS1}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="marcador"):
        gerar_instalador("http://x", script=ruim)


def test_pacote_sem_url_ainda_e_valido() -> None:
    z = zipfile.ZipFile(io.BytesIO(montar_pacote("")))
    assert z.read("servidor.txt").decode().strip() == ""
