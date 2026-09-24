"""O que o assistente confere antes de pedir os dados do administrador.

O texto que sai daqui é lido por gente sem contexto técnico e por qualquer
pessoa que abra /setup antes do primeiro acesso: descreve o que está errado sem
citar DSN, senha, host nem mensagem de exceção.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import obter_config
from app.db.base import criar_sessao

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Verificacao:
    id: str
    rotulo: str
    ok: bool
    detalhe: str | None = None


def setup_concluido() -> bool | None:
    """True se já existe usuário; None se não deu para saber (banco fora do ar,
    migrations ainda não aplicadas). Quem chama trata None como 'não sei'."""
    try:
        with criar_sessao() as s:
            return bool(s.execute(text("SELECT setup_concluido()")).scalar_one())
    except Exception:
        log.warning("não foi possível consultar se o setup foi concluído", exc_info=False)
        return None


def _banco() -> Verificacao:
    try:
        with criar_sessao() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        return Verificacao("banco", "Banco de dados", False,
                           "Não foi possível conectar ao banco de dados.")
    return Verificacao("banco", "Banco de dados", True)


def _esquema() -> Verificacao:
    try:
        with criar_sessao() as s:
            pronto = s.execute(
                text("SELECT to_regprocedure('setup_concluido()') IS NOT NULL "
                     "AND to_regclass('public.escritorio') IS NOT NULL")
            ).scalar_one()
    except Exception:
        return Verificacao("esquema", "Estrutura do banco", False,
                           "Não foi possível conferir a estrutura do banco.")
    if not pronto:
        return Verificacao("esquema", "Estrutura do banco", False,
                           "A estrutura do banco ainda não foi criada.")
    return Verificacao("esquema", "Estrutura do banco", True)


def _redis(url: str) -> Verificacao:
    try:
        import redis  # sob demanda: a instalação local nem tem o pacote

        redis.from_url(url, socket_connect_timeout=2).ping()
    except Exception:
        return Verificacao("redis", "Fila de tarefas", False,
                           "Não foi possível conectar à fila de tarefas.")
    return Verificacao("redis", "Fila de tarefas", True)


def verificar_sistema() -> list[Verificacao]:
    banco = _banco()
    esquema = (
        _esquema()
        if banco.ok
        else Verificacao("esquema", "Estrutura do banco", False,
                         "Aguardando o banco de dados.")
    )
    verificacoes = [banco, esquema]
    url_redis = obter_config().redis_url
    if url_redis:  # sem Redis configurado (instalação local), não há o que conferir
        verificacoes.append(_redis(url_redis))
    return verificacoes
