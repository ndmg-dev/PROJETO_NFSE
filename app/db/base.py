"""Sessão e base declarativa, com o escopo de tenant aplicado no banco."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import obter_config


class Base(DeclarativeBase):
    pass


_engine = None
_Sessao = None


def engine():  # type: ignore[no-untyped-def]
    global _engine, _Sessao
    if _engine is None:
        _engine = create_engine(obter_config().database_url, pool_pre_ping=True)
        _Sessao = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def sessao_do_escritorio(escritorio_id: UUID) -> Iterator[Session]:
    """Abre sessão com RLS ativa para um escritório.

    O `SET LOCAL` vale só dentro da transação, então não vaza entre requisições
    de um pool. O filtro por escritório passa a ser do Postgres, não da
    aplicação — a §4 exige isso explicitamente.
    """
    engine()
    assert _Sessao is not None
    with _Sessao() as s:
        # set_config(..., is_local=true) é equivalente a SET LOCAL, mas é
        # função: aceita parâmetro vinculado. SET LOCAL é comando utilitário e
        # exigiria interpolar a string — porta aberta para injeção.
        s.execute(
            text("SELECT set_config('app.escritorio_id', :eid, true)"),
            {"eid": str(escritorio_id)},
        )
        yield s
