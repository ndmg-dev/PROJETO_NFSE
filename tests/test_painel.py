"""Painel web (app/web/index.html).

O painel lista empresas cujos campos de texto livre (razão social, regime) são
digitados por qualquer operador. Interpolá-los em `innerHTML` executaria
marcação alheia no navegador de quem abrir a lista — XSS armazenado. A
correção foi verificada uma vez, com o painel real rodando em jsdom e dados
hostis; este teste é só a guarda barata que impede o padrão de voltar.

LIMITE: é uma checagem estática do fonte, não uma execução em navegador.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WEB = Path(__file__).resolve().parents[1] / "app" / "web"
INDEX = WEB / "index.html"
PAGINAS = [WEB / "index.html", WEB / "setup.html", WEB / "instalar.html"]


def test_painel_e_servido_na_raiz() -> None:
    from app.api.main import app

    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: p.name)
def test_pagina_nao_monta_html_a_partir_de_dados(pagina: Path) -> None:
    js = pagina.read_text(encoding="utf-8")

    atribuicoes = re.findall(r"innerHTML\s*=\s*([^;\n]+)", js)
    nao_vazias = [a.strip() for a in atribuicoes if a.strip() not in {'""', "''"}]
    assert not nao_vazias, (
        "innerHTML recebendo conteúdo (risco de XSS armazenado): " f"{nao_vazias}"
    )

    for api_perigosa in ("insertAdjacentHTML", "outerHTML", "document.write"):
        assert api_perigosa not in js, f"{api_perigosa} monta HTML a partir de string"


def test_login_do_painel_nao_traz_credenciais_prontas() -> None:
    """Sobrou do PR do painel: e-mail e senha de teste pré-preenchidos, e uma
    dica anunciando-os. Com o assistente de primeiro acesso esse usuário não
    existe, e anunciar senha padrão é risco."""
    html = INDEX.read_text(encoding="utf-8")
    assert "senha123" not in html
    assert "admin@example.com" not in html
