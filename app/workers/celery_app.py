"""Celery e agendamento (spec §3.4, §9)."""

from __future__ import annotations

import os

from celery import Celery

broker = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("nfse", broker=broker, backend=broker)
celery_app.conf.update(
    task_acks_late=True,          # tarefa só sai da fila quando termina
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # paraleliza por empresa, não por NSU
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    timezone="America/Sao_Paulo",
    broker_connection_retry_on_startup=True,
)

# AGENDA REVOGADA por §3.3-A (22/09/2026): o servidor não tem mais certificado
# para chamar o ADN sozinho, então não há mais "sincronizar a cada 4h" nem
# "varrer eventos à noite" rodando sem o agente. A sincronização passou a ser
# sob demanda — acionada pelo contador, atendida pelo agente da estação dele
# (§6, POST /empresas/{id}/sync). Alerta de certificado vencendo também muda
# de dono: quem vê a validade agora é o agente, lendo a store do Windows, não
# uma tabela central que deixou de existir.
#
# Fica em aberto para a etapa "agente completo": como um alerta de validade ou
# uma varredura de eventos pode ser reintroduzida sem violar "sob demanda" —
# por exemplo, o agente reportar a validade a cada sincronização que ele já
# fizer por iniciativa do contador, em vez de o servidor perguntar sozinho.
celery_app.conf.beat_schedule: dict[str, dict[str, object]] = {}
