"""Isolamento multi-tenant no banco (spec §8).

A spec manda testar explicitamente que ler dados de outro tenant FALHA. Estes
testes rodam contra Postgres real: RLS não se testa com mock.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ProgrammingError


def test_ve_apenas_o_proprio_escritorio(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    a, b = dois_escritorios
    with engine.connect() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', :e, false)"), {"e": str(a)})
        linhas = c.execute(text("SELECT escritorio_id FROM empresa")).scalars().all()
    assert linhas == [a], "vazou empresa de outro escritório"


def test_nao_ve_o_outro_nem_com_filtro_explicito(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    """Pedir explicitamente os dados do vizinho não devolve nada."""
    a, b = dois_escritorios
    with engine.connect() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', :e, false)"), {"e": str(a)})
        n = c.execute(text("SELECT count(*) FROM empresa WHERE escritorio_id = :b"),
                      {"b": b}).scalar_one()
    assert n == 0


def test_sem_tenant_definido_nao_ve_nada(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    """Falha fechada: esquecer o SET não é o mesmo que ver tudo."""
    with engine.connect() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', '', false)"))
        n = c.execute(text("SELECT count(*) FROM empresa")).scalar_one()
    assert n == 0


def test_nao_consegue_inserir_para_outro_escritorio(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    """WITH CHECK impede plantar linha no tenant vizinho."""
    a, b = dois_escritorios
    with engine.connect() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', :e, false)"), {"e": str(a)})
        with pytest.raises(ProgrammingError, match="row-level security"):
            c.execute(
                text("""INSERT INTO empresa
                        (id, escritorio_id, cnpj, cnpj_raiz, razao_social, ultimo_nsu,
                         sync_ativo)
                        VALUES (:id, :e, '11111111000111', '11111111', 'Invasora', 0, true)"""),
                {"id": uuid.uuid4(), "e": b},
            )


def test_nao_consegue_atualizar_o_outro(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    a, b = dois_escritorios
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', :e, true)"), {"e": str(a)})
        afetadas = c.execute(
            text("UPDATE empresa SET razao_social = 'sequestrada' "
                 "WHERE escritorio_id = :b"), {"b": b}
        ).rowcount
    assert afetadas == 0

    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', :e, true)"), {"e": str(b)})
        nome = c.execute(text("SELECT razao_social FROM empresa")).scalar_one()
    assert nome != "sequestrada"


def test_nao_consegue_apagar_o_outro(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    a, b = dois_escritorios
    with engine.begin() as c:
        c.execute(text("SELECT set_config('app.escritorio_id', :e, true)"), {"e": str(a)})
        afetadas = c.execute(
            text("DELETE FROM empresa WHERE escritorio_id = :b"), {"b": b}
        ).rowcount
    assert afetadas == 0


def test_rls_esta_forcada_em_todas_as_tabelas(engine: Engine) -> None:
    """Sem FORCE, o dono da tabela ignora a política — e a app é o dono."""
    from app.db.models import TABELAS_COM_RLS

    with engine.connect() as c:
        linhas = dict(
            c.execute(
                text("SELECT relname, relforcerowsecurity FROM pg_class "
                     "WHERE relname = ANY(:t)"),
                {"t": list(TABELAS_COM_RLS)},
            ).all()
        )
    sem_force = [t for t in TABELAS_COM_RLS if not linhas.get(t)]
    assert not sem_force, f"RLS não forçada em: {sem_force}"


def test_set_local_nao_vaza_entre_transacoes(engine: Engine, dois_escritorios) -> None:  # type: ignore[no-untyped-def]
    """A garantia que permite usar pool de conexões com segurança."""
    a, _ = dois_escritorios
    with engine.connect() as c:
        with c.begin():
            c.execute(text("SELECT set_config('app.escritorio_id', :e, true)"), {"e": str(a)})
            assert c.execute(text("SELECT count(*) FROM empresa")).scalar_one() == 1
        # nova transação na MESMA conexão: o escopo morreu junto com a anterior
        with c.begin():
            assert c.execute(text("SELECT count(*) FROM empresa")).scalar_one() == 0
