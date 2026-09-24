from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.seguranca import hash_senha

pytest.register_assert_rewrite("tests")


def _url(nome: str) -> str:
    url = os.environ.get(nome)
    if not url:
        pytest.skip(f"{nome} não definida — teste precisa do Postgres")
    return url


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Conexão como a APLICAÇÃO conecta: papel sem privilégio, RLS valendo."""
    eng = create_engine(_url("DATABASE_URL"), pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def engine_admin() -> Iterator[Engine]:
    """Dono do schema, para montar cenário. A aplicação nunca usa isto."""
    eng = create_engine(_url("ADMIN_DATABASE_URL"), pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture
def dois_escritorios(engine_admin: Engine) -> Iterator[tuple[uuid.UUID, uuid.UUID]]:
    """Dois tenants com uma empresa cada. Limpa tudo no fim."""
    a, b = uuid.uuid4(), uuid.uuid4()
    with engine_admin.begin() as c:
        for eid, nome in ((a, "Escritório A"), (b, "Escritório B")):
            c.execute(text("INSERT INTO escritorio (id, nome) VALUES (:i, :n)"),
                      {"i": eid, "n": nome})
            c.execute(
                text("""INSERT INTO empresa
                        (id, escritorio_id, cnpj, cnpj_raiz, razao_social, ultimo_nsu,
                         sync_ativo)
                        VALUES (:id, :e, :cnpj, :raiz, :rs, 0, true)"""),
                {"id": uuid.uuid4(), "e": eid, "cnpj": "07199546000162",
                 "raiz": "07199546", "rs": f"Cliente de {nome}"},
            )
    yield a, b
    with engine_admin.begin() as c:
        for eid in (a, b):
            c.execute(text("DELETE FROM empresa WHERE escritorio_id = :e"), {"e": eid})
            c.execute(text("DELETE FROM escritorio WHERE id = :e"), {"e": eid})


@pytest.fixture
def cliente() -> TestClient:
    from app.api.main import app

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def cenario(engine_admin: Engine):  # type: ignore[no-untyped-def]
    """Dois escritórios, um admin em cada, uma empresa em cada."""
    # Import aqui, não no topo: tests.apoio_api precisa ser importado DEPOIS de
    # pytest.register_assert_rewrite("tests"), senão os asserts dele não são
    # reescritos e as mensagens de falha ficam pobres.
    from tests.apoio_api import CNPJ, SENHA_USUARIO

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
            # Ordem por dependência: evento -> nota -> bruto -> empresa.
            for tabela in ("nfse_evento", "nfse", "dfe_bruto"):
                c.execute(text(f"DELETE FROM {tabela} WHERE escritorio_id=:e"),
                          {"e": v["escritorio"]})
            c.execute(text("DELETE FROM empresa WHERE escritorio_id=:e"), {"e": v["escritorio"]})
            c.execute(text("DELETE FROM usuario WHERE escritorio_id=:e"), {"e": v["escritorio"]})
            c.execute(text("DELETE FROM escritorio WHERE id=:e"), {"e": v["escritorio"]})
