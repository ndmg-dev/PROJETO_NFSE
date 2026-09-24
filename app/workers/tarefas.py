"""Tarefas Celery.

A lógica de verdade mora em `sincronizacao.py`, que é puro e testável. Aqui
fica só a casca: lock, montagem das dependências e registro do resultado.

Sincronização passou a ser sob demanda por decisão de arquitetura (spec
§3.3-A, 22/09/2026): o servidor não tem mais certificado para chamar o ADN
sozinho — quem chama é o agente da estação do contador. `sincronizar_todas`
não existe mais como tarefa periódica; o disparo é por empresa, vindo de
`POST /empresas/{id}/sync`, e depende do protocolo agente↔servidor que ainda
não foi desenhado (etapa "agente completo").

Não há mais tarefa de alerta de certificado vencendo: quem vê a validade
agora é o agente, lendo a store do Windows — não existe mais tabela central
com essa informação.
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
    o checkpoint é sequencial e duas varreduras se atropelariam. Continua
    valendo no modelo sob demanda: dois cliques do mesmo contador, ou dois
    contadores da mesma empresa, não podem sincronizar ao mesmo tempo.
    """
    url = obter_config().redis_url
    if not url:
        raise RuntimeError("REDIS_URL não configurada: os workers precisam do Redis")
    cliente = redis.from_url(url)
    chave = f"sync:{empresa_id}"
    obtido = bool(cliente.set(chave, "1", nx=True, ex=TTL_LOCK_S))
    try:
        yield obtido
    finally:
        if obtido:
            cliente.delete(chave)


@celery_app.task(name="app.workers.tarefas.sincronizar_empresa")
def sincronizar_empresa_task(empresa_id: str) -> None:
    """Atende um pedido de sincronização sob demanda de uma empresa.

    Bloqueada até o protocolo agente↔servidor existir: o loop em
    `sincronizacao.py` está pronto e testado, mas ele espera um `cliente`
    capaz de `buscar_dfe(nsu)` — e essa implementação, no novo desenho, precisa
    pedir ao agente da estação do contador e esperar a resposta, em vez de
    chamar o ADN diretamente. Esse protocolo (fila de pedidos, autenticação do
    agente, casamento por CNPJ raiz) é o que falta desenhar.
    """
    raise NotImplementedError(
        "Aguardando o protocolo agente↔servidor (spec §3.3-A). O loop de "
        "sincronização está pronto em app/workers/sincronizacao.py; falta o "
        "transporte que peça ao agente da estação do contador, em vez de "
        "chamar o ADN diretamente pelo servidor."
    )
