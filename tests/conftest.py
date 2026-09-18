from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

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
