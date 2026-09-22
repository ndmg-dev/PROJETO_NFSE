"""Celery e agendamento (spec §3.4, §9)."""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

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

celery_app.conf.beat_schedule = {
    # A cada 4h em dias úteis (spec §3.4).
    "sincronizar-empresas": {
        "task": "app.workers.tarefas.sincronizar_todas",
        "schedule": crontab(hour="6,10,14,18", minute=0, day_of_week="mon-fri"),
    },
    # Eventos chegam depois da nota original, então varredura diária própria.
    "varrer-eventos": {
        "task": "app.workers.tarefas.varrer_eventos",
        "schedule": crontab(hour=22, minute=30),
    },
    # Alerta de certificado vencendo em 30/15/7 dias (spec §8).
    "alertar-certificados": {
        "task": "app.workers.tarefas.alertar_certificados_vencendo",
        "schedule": crontab(hour=7, minute=0),
    },
}
