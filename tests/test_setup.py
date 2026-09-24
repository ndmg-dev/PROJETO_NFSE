"""Primeiro acesso: código, limite de tentativas, atomicidade e trava final.

Os testes de banco exigem a tabela de usuários VAZIA (é o estado que o setup
pressupõe). Se houver dado real no banco de desenvolvimento, eles se pulam em
vez de mexer nele.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.api.routers import setup as roteador
from app.core.config import obter_config
from app.setup.codigo import codigo_confere, codigo_de_configuracao
from app.setup.limite import LimitadorDeTentativas

SEGREDO = "segredo-de-teste-com-mais-de-trinta-e-dois-bytes"
NOME = "Escritório do Setup"


def dados(codigo: str, **mudancas: str) -> dict[str, str]:
    base = {"codigo": codigo, "escritorio": NOME, "email": "Admin@Exemplo.com",
            "senha": "uma-senha-longa-123"}
    return {**base, **mudancas}


def codigo_real() -> str:
    return codigo_de_configuracao(obter_config().jwt_secret.get_secret_value())


@pytest.fixture
def banco_vazio(engine_admin: Engine) -> Iterator[None]:
    with engine_admin.begin() as c:
        if c.execute(text("SELECT count(*) FROM usuario")).scalar_one():
            pytest.skip("o banco tem usuários; o teste de setup exige banco sem usuários")
    roteador.LIMITE_POR_ORIGEM.limpar_tudo()
    roteador.LIMITE_GLOBAL.limpar_tudo()
    yield
    with engine_admin.begin() as c:
        c.execute(text("DELETE FROM audit_log WHERE acao = 'setup.primeiro_acesso'"))
        c.execute(text("DELETE FROM usuario"))
        c.execute(text("DELETE FROM escritorio WHERE nome = :n"), {"n": NOME})
    roteador.LIMITE_POR_ORIGEM.limpar_tudo()
    roteador.LIMITE_GLOBAL.limpar_tudo()


# ================================================================== o código ===


def test_codigo_tem_o_formato_esperado() -> None:
    codigo = codigo_de_configuracao(SEGREDO)
    assert len(codigo) == 9 and codigo[4] == "-"
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in codigo.replace("-", ""))


def test_codigo_e_estavel_e_depende_do_segredo() -> None:
    assert codigo_de_configuracao(SEGREDO) == codigo_de_configuracao(SEGREDO)
    assert codigo_de_configuracao(SEGREDO) != codigo_de_configuracao(SEGREDO + "x")


@pytest.mark.parametrize("variacao", [str.upper, str.lower, lambda c: c.replace("-", ""),
                                      lambda c: f"  {c} ", lambda c: c.replace("-", " ")])
def test_codigo_tolera_caixa_hifen_e_espaco(variacao) -> None:  # type: ignore[no-untyped-def]
    assert codigo_confere(variacao(codigo_de_configuracao(SEGREDO)), SEGREDO)


@pytest.mark.parametrize("errado", ["", "AAAA-AAAA", "K7QH", "não-é-código"])
def test_codigo_errado_nao_confere(errado: str) -> None:
    assert not codigo_confere(errado, SEGREDO)


# ============================================================ limite de tentativas ===


def test_limitador_bloqueia_apos_o_maximo_e_libera_com_o_tempo() -> None:
    agora = [0.0]
    lim = LimitadorDeTentativas(maximo=3, janela_s=60, relogio=lambda: agora[0])
    for _ in range(3):
        assert not lim.bloqueado("x")
        lim.registrar_falha("x")
    assert lim.bloqueado("x")
    assert not lim.bloqueado("outra-origem")
    agora[0] = 61.0
    assert not lim.bloqueado("x"), "a janela deveria ter expirado"


# ================================================================ o status ===


def test_status_com_banco_vazio(cliente: TestClient, banco_vazio) -> None:  # type: ignore[no-untyped-def]
    r = cliente.get("/setup/status")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["configurado"] is False
    assert {v["id"] for v in corpo["verificacoes"]} == {"banco", "esquema", "redis"}
    assert all(v["ok"] for v in corpo["verificacoes"])


def test_status_apos_configurado_nao_expoe_infraestrutura(  # type: ignore[no-untyped-def]
    cliente: TestClient, cenario
) -> None:
    corpo = cliente.get("/setup/status").json()
    assert corpo == {"configurado": True, "verificacoes": []}


# ================================================================ o setup ===


def test_setup_completo_e_login_com_o_que_foi_criado(  # type: ignore[no-untyped-def]
    cliente: TestClient, banco_vazio, engine_admin
) -> None:
    r = cliente.post("/setup", json=dados(codigo_real()))
    assert r.status_code == 201, r.text

    login = cliente.post("/auth/login",
                         json={"email": "admin@exemplo.com", "senha": "uma-senha-longa-123"})
    assert login.status_code == 200, "o admin criado não consegue entrar"
    # e-mail digitado com maiúsculas também entra: é normalizado nos dois lados
    assert cliente.post("/auth/login", json={
        "email": "ADMIN@EXEMPLO.COM", "senha": "uma-senha-longa-123"}).status_code == 200

    with engine_admin.begin() as c:
        papel, nome = c.execute(text(
            "SELECT u.papel, e.nome FROM usuario u JOIN escritorio e "
            "ON e.id = u.escritorio_id")).one()
        auditoria = c.execute(text(
            "SELECT count(*) FROM audit_log WHERE acao = 'setup.primeiro_acesso'")).scalar_one()
    assert (papel, nome) == ("admin", NOME)
    assert auditoria == 1


def test_a_senha_nao_fica_em_claro(cliente: TestClient, banco_vazio, engine_admin) -> None:  # type: ignore[no-untyped-def]
    cliente.post("/setup", json=dados(codigo_real()))
    with engine_admin.begin() as c:
        gravado = c.execute(text("SELECT senha_hash FROM usuario")).scalar_one()
    assert "uma-senha-longa-123" not in gravado and gravado.startswith("$2")


def test_codigo_errado_nao_cria_nada(cliente: TestClient, banco_vazio, engine_admin) -> None:  # type: ignore[no-untyped-def]
    r = cliente.post("/setup", json=dados("AAAA-AAAA"))
    assert r.status_code == 403
    with engine_admin.begin() as c:
        assert c.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM escritorio WHERE nome = :n"),
                         {"n": NOME}).scalar_one() == 0


def test_codigo_pode_vir_em_minuscula_e_sem_hifen(cliente: TestClient, banco_vazio) -> None:  # type: ignore[no-untyped-def]
    assert cliente.post("/setup", json=dados(
        codigo_real().replace("-", "").lower())).status_code == 201


def test_depois_de_configurado_o_setup_tranca_mesmo_com_o_codigo_certo(  # type: ignore[no-untyped-def]
    cliente: TestClient, banco_vazio
) -> None:
    assert cliente.post("/setup", json=dados(codigo_real())).status_code == 201
    segundo = cliente.post("/setup", json=dados(codigo_real(), email="outro@exemplo.com"))
    assert segundo.status_code == 409


def test_sistema_com_usuarios_existentes_ja_esta_configurado(  # type: ignore[no-untyped-def]
    cliente: TestClient, cenario
) -> None:
    assert cliente.post("/setup", json=dados(codigo_real())).status_code == 409


def test_seis_codigos_errados_bloqueiam_ate_o_codigo_certo(  # type: ignore[no-untyped-def]
    cliente: TestClient, banco_vazio, engine_admin
) -> None:
    for _ in range(5):
        assert cliente.post("/setup", json=dados("AAAA-AAAA")).status_code == 403
    bloqueado = cliente.post("/setup", json=dados(codigo_real()))
    assert bloqueado.status_code == 429, "força bruta deveria estar bloqueada"
    with engine_admin.begin() as c:
        assert c.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 0


@pytest.mark.parametrize(
    "mudanca",
    [{"senha": "curta"}, {"email": "isto-nao-e-email"}, {"escritorio": "X"}, {"escritorio": ""}],
)
def test_dados_invalidos_sao_422_e_nao_gastam_tentativa(  # type: ignore[no-untyped-def]
    cliente: TestClient, banco_vazio, mudanca: dict[str, str]
) -> None:
    assert cliente.post("/setup", json=dados(codigo_real(), **mudanca)).status_code == 422


def test_dois_setups_simultaneos_criam_um_administrador_so(  # type: ignore[no-untyped-def]
    banco_vazio, engine_admin
) -> None:
    """A atomicidade do banco (advisory lock): o segundo espera, vê o usuário do
    primeiro e falha, em vez de criar um segundo administrador."""
    from app.api.main import app

    codigo = codigo_real()

    def tentar(email: str) -> int:
        return TestClient(app, raise_server_exceptions=False).post(
            "/setup", json=dados(codigo, email=email)).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codigos = list(pool.map(tentar, [f"admin{i}@exemplo.com" for i in range(6)]))

    assert sorted(codigos) == [201, 409, 409, 409, 409, 409], codigos
    with engine_admin.begin() as c:
        assert c.execute(text("SELECT count(*) FROM usuario")).scalar_one() == 1


# ============================================================ raiz e páginas ===


def test_raiz_manda_para_o_setup_enquanto_nao_configurado(banco_vazio) -> None:  # type: ignore[no-untyped-def]
    from app.api.main import app

    r = TestClient(app).get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/setup"


def test_raiz_serve_o_painel_depois_de_configurado(cenario) -> None:  # type: ignore[no-untyped-def]
    from app.api.main import app

    r = TestClient(app).get("/", follow_redirects=False)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_assistente_e_servido(cliente: TestClient) -> None:
    r = cliente.get("/setup")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
