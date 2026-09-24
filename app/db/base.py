"""Sessão e base declarativa, com o escopo de tenant aplicado no banco."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Session, SessionTransaction, sessionmaker

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
def criar_sessao() -> Iterator[Session]:
    """Sessão sem escopo de tenant. Quem usa é responsável por fixá-lo."""
    engine()
    assert _Sessao is not None
    with _Sessao() as s:
        yield s


def _fixar_tenant_a_cada_transacao(sessao: Session, escritorio_id: UUID) -> None:
    """Reaplica o escopo de tenant em TODA transação que a sessão abrir.

    set_config(..., is_local=true) vale só até o fim da transação. Numa sessão
    que faz commit no meio do trabalho (o checkpoint por lote da sincronização
    faz), a transação seguinte começaria sem tenant e a RLS não liberaria linha
    nenhuma: leitura vazia e INSERT recusado. O gancho after_begin roda no início
    de cada transação, então o escopo nunca se perde.
    """
    eid = str(escritorio_id)

    @event.listens_for(sessao, "after_begin")
    def _aplicar(
        _sessao: Session, _transacao: SessionTransaction, conexao: Connection
    ) -> None:
        # set_config aceita parâmetro vinculado; SET LOCAL exigiria interpolar
        # a string — porta aberta para injeção.
        conexao.execute(
            text("SELECT set_config('app.escritorio_id', :eid, true)"), {"eid": eid}
        )


@contextmanager
def sessao_do_escritorio(escritorio_id: UUID) -> Iterator[Session]:
    """Abre sessão com RLS ativa para um escritório, em todas as transações.

    O filtro por escritório é do Postgres, não da aplicação (spec §4), e o
    escopo é local à transação, então não vaza entre requisições de um pool.
    """
    engine()
    assert _Sessao is not None
    with _Sessao() as s:
        _fixar_tenant_a_cada_transacao(s, escritorio_id)
        yield s
