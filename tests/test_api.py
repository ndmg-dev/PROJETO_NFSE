"""API: autenticação e escopo de tenant.

Upload de certificado foi removido daqui por decisão de arquitetura (spec
§3.3-A, 22/09/2026): o .pfx nunca sobe para o servidor, então não há mais
endpoint, nem cifra, nem teste de vazamento de .pfx nesta camada — o
certificado passou a ser problema exclusivo do agente local.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.apoio_api import SENHA_USUARIO, entrar

# ------------------------------------------------------------------ auth ---

def test_health_nao_exige_token(cliente: TestClient) -> None:
    assert cliente.get("/health").json() == {"status": "ok"}


def test_login_e_lista(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.get("/empresas", headers=entrar(cliente, "a@teste.com"))
    assert r.status_code == 200
    assert [e["razao_social"] for e in r.json()] == ["Cliente a"]


def test_senha_errada(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.post("/auth/login", json={"email": "a@teste.com", "senha": "errada-mas-longa"})
    assert r.status_code == 401


def test_usuario_inexistente_da_o_mesmo_erro(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    """Diferenciar entrega enumeração de contas."""
    r1 = cliente.post("/auth/login", json={"email": "a@teste.com", "senha": "errada-mas-longa"})
    r2 = cliente.post("/auth/login",
                      json={"email": "ninguem@teste.com", "senha": "errada-mas-longa"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_sem_token(cliente: TestClient) -> None:
    assert cliente.get("/empresas").status_code == 401


def test_token_adulterado(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    cabecalho = entrar(cliente, "a@teste.com")
    cabecalho["Authorization"] = cabecalho["Authorization"][:-2] + "xx"
    assert cliente.get("/empresas", headers=cabecalho).status_code == 401


def test_refresh_nao_serve_como_access(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.post("/auth/login", json={"email": "a@teste.com", "senha": SENHA_USUARIO})
    refresh = r.json()["refresh_token"]
    assert cliente.get(
        "/empresas", headers={"Authorization": f"Bearer {refresh}"}
    ).status_code == 401


# ---------------------------------------------------------- multi-tenant ---

def test_nao_lista_empresa_de_outro_escritorio(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.get("/empresas", headers=entrar(cliente, "a@teste.com"))
    assert all(e["razao_social"] != "Cliente b" for e in r.json())


def test_nao_le_empresa_de_outro_por_id(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    """O teste que a spec §8 exige: acesso cross-tenant DEVE falhar."""
    alvo = cenario["b"]["empresa"]
    r = cliente.get(f"/empresas/{alvo}", headers=entrar(cliente, "a@teste.com"))
    assert r.status_code == 404, "vazou empresa de outro escritório"


# --------------------------------------------------------------- cadastro ---

def test_cnpj_invalido_no_cadastro(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.post("/empresas", headers=entrar(cliente, "a@teste.com"),
                     json={"cnpj": "123", "razao_social": "X"})
    assert r.status_code == 422


def test_cadastro_calcula_a_raiz(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.post("/empresas", headers=entrar(cliente, "a@teste.com"),
                     json={"cnpj": "11.222.333/0001-81", "razao_social": "Nova"})
    assert r.status_code == 201, r.text
    assert r.json()["cnpj"] == "11222333000181"
    assert r.json()["cnpj_raiz"] == "11222333"
