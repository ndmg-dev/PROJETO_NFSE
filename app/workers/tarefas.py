"""Tarefas Celery.

A lógica de verdade mora em `sincronizacao.py`, que é puro e testável. Aqui
fica só a casca: lock, montagem das dependências e registro do resultado.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import redis

from app.core.config import obter_config
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)

TTL_LOCK_S = 15 * 60


@contextmanager
def lock_de_empresa(empresa_id: UUID) -> Iterator[bool]:
    """Impede duas sincronizações concorrentes da mesma empresa (spec §3.4).

    Paralelizar por empresa é seguro; por NSU dentro da mesma empresa, não —
    o checkpoint é sequencial e duas varreduras se atropelariam.
    """
    cliente = redis.from_url(obter_config().redis_url)
    chave = f"sync:{empresa_id}"
    obtido = bool(cliente.set(chave, "1", nx=True, ex=TTL_LOCK_S))
    try:
        yield obtido
    finally:
        if obtido:
            cliente.delete(chave)


@celery_app.task(name="app.workers.tarefas.sincronizar_todas")
def sincronizar_todas() -> None:
    """Enfileira uma tarefa por empresa ativa. Não sincroniza em série."""
    raise NotImplementedError(
        "Aguardando o contrato do ADN (app/adn/contrato.py, VERIFICADO=False). "
        "O loop está pronto e testado em app/workers/sincronizacao.py; falta "
        "apenas montar ClienteADN com o certificado real."
    )


@celery_app.task(name="app.workers.tarefas.varrer_eventos")
def varrer_eventos() -> None:
    raise NotImplementedError("Aguardando o contrato do ADN.")


@celery_app.task(name="app.workers.tarefas.alertar_certificados_vencendo")
def alertar_certificados_vencendo() -> None:
    raise NotImplementedError("Aguardando integração de notificação.")
