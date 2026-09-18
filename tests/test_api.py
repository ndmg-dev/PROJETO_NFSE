"""API: autenticação, escopo de tenant e não vazamento de certificado.

Os testes de vazamento (spec §8) varrem o corpo inteiro da resposta e os logs,
não só os campos que lembramos de checar.
"""

from __future__ import annotations

import io
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.seguranca import hash_senha
from tests.test_certificado import CNPJ, SENHA, gerar_pfx

SENHA_USUARIO = "senha-de-teste-123"


@pytest.fixture
def cliente() -> TestClient:
    from app.api.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cenario(engine_admin: Engine):  # type: ignore[no-untyped-def]
    """Dois escritórios, um admin em cada, uma empresa em cada."""
    dados = {}
    with engine_admin.begin() as c:
        for rotulo in ("a", "b"):
            eid, uid, empid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            c.execute(text("INSERT INTO escritorio (id, nome) VALUES (:i, :n)"),
                      {"i": eid, "n": f"Escritório {rotulo}"})
            c.execute(
                text("""INSERT INTO usuario (id, escritorio_id, email, senha_hash,
                        papel, ativo) VALUES (:i, :e, :m, :h, 'admin', true)"""),
                {"i": uid, "e": eid, "m": f"{rotulo}@teste.com",
                 "h": hash_senha(SENHA_USUARIO)},
            )
            c.execute(
                text("""INSERT INTO empresa (id, escritorio_id, cnpj, cnpj_raiz,
                        razao_social, ultimo_nsu, sync_ativo)
                        VALUES (:i, :e, :c, :r, :rs, 0, true)"""),
                {"i": empid, "e": eid, "c": CNPJ, "r": CNPJ[:8],
                 "rs": f"Cliente {rotulo}"},
            )
            dados[rotulo] = {"escritorio": eid, "usuario": uid, "empresa": empid}
    yield dados
    with engine_admin.begin() as c:
        for v in dados.values():
            c.execute(text("DELETE FROM certificado WHERE escritorio_id=:e"),
                      {"e": v["escritorio"]})
            c.execute(text("DELETE FROM empresa WHERE escritorio_id=:e"), {"e": v["escritorio"]})
            c.execute(text("DELETE FROM usuario WHERE escritorio_id=:e"), {"e": v["escritorio"]})
            c.execute(text("DELETE FROM escritorio WHERE id=:e"), {"e": v["escritorio"]})


def entrar(cliente: TestClient, email: str) -> dict[str, str]:
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA_USUARIO})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


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


def test_nao_envia_certificado_para_empresa_de_outro(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    alvo = cenario["b"]["empresa"]
    r = cliente.post(
        f"/empresas/{alvo}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(gerar_pfx()), "application/x-pkcs12")},
        data={"senha": SENHA.decode()},
    )
    assert r.status_code == 404


# ------------------------------------------------------------ certificado ---

def test_upload_devolve_so_metadados(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    pfx = gerar_pfx()
    r = cliente.post(
        f"/empresas/{cenario['a']['empresa']}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(pfx), "application/x-pkcs12")},
        data={"senha": SENHA.decode()},
    )
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["titular_cnpj"] == CNPJ
    assert set(corpo) == {
        "id", "cnpj_raiz", "titular_cnpj", "titular_nome",
        "valido_de", "valido_ate", "ativo", "dias_para_vencer",
    }


def test_resposta_nao_contem_pfx_nem_senha(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    """Varre o corpo cru, não só os campos que lembramos de checar."""
    pfx = gerar_pfx()
    r = cliente.post(
        f"/empresas/{cenario['a']['empresa']}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(pfx), "application/x-pkcs12")},
        data={"senha": SENHA.decode()},
    )
    bruto = r.content
    assert SENHA not in bruto
    assert pfx[:64] not in bruto
    assert b"pfx_ciphered" not in bruto
    assert b"senha_ciphered" not in bruto
    assert b"PRIVATE KEY" not in bruto


def test_senha_nao_aparece_em_log(cliente: TestClient, cenario, caplog) -> None:  # type: ignore[no-untyped-def]
    with caplog.at_level(logging.DEBUG):
        cliente.post(
            f"/empresas/{cenario['a']['empresa']}/certificado",
            headers=entrar(cliente, "a@teste.com"),
            files={"arquivo": ("c.pfx", io.BytesIO(gerar_pfx()), "application/x-pkcs12")},
            data={"senha": SENHA.decode()},
        )
    assert SENHA.decode() not in caplog.text


def test_senha_errada_no_upload(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    r = cliente.post(
        f"/empresas/{cenario['a']['empresa']}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(gerar_pfx()), "application/x-pkcs12")},
        data={"senha": "errada"},
    )
    assert r.status_code == 422
    assert "errada" not in r.text


def test_recusa_certificado_de_raiz_diferente(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    """O ADN valida o CNPJ raiz — recusar aqui evita falha só na sincronização."""
    outro = gerar_pfx(cn="OUTRA EMPRESA LTDA:11222333000181")
    r = cliente.post(
        f"/empresas/{cenario['a']['empresa']}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(outro), "application/x-pkcs12")},
        data={"senha": SENHA.decode()},
    )
    assert r.status_code == 422
    assert "raiz" in r.json()["detail"]


def test_recusa_certificado_vencido(cliente: TestClient, cenario) -> None:  # type: ignore[no-untyped-def]
    vencido = gerar_pfx(dias_validade=-2)
    r = cliente.post(
        f"/empresas/{cenario['a']['empresa']}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(vencido), "application/x-pkcs12")},
        data={"senha": SENHA.decode()},
    )
    assert r.status_code == 422


def test_pfx_fica_cifrado_no_banco(cliente: TestClient, cenario, engine_admin) -> None:  # type: ignore[no-untyped-def]
    pfx = gerar_pfx()
    cliente.post(
        f"/empresas/{cenario['a']['empresa']}/certificado",
        headers=entrar(cliente, "a@teste.com"),
        files={"arquivo": ("c.pfx", io.BytesIO(pfx), "application/x-pkcs12")},
        data={"senha": SENHA.decode()},
    )
    with engine_admin.begin() as c:
        linha = c.execute(
            text("SELECT pfx_ciphered, senha_ciphered FROM certificado "
                 "WHERE escritorio_id = :e"),
            {"e": cenario["a"]["escritorio"]},
        ).one()
    assert bytes(linha[0]) != pfx, "o .pfx foi gravado em claro"
    assert SENHA not in bytes(linha[1])


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
