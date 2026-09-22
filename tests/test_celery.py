"""Configuração do Celery (spec §3.4, §9, e o adendo de arquitetura §3.3-A)."""

from __future__ import annotations

import pytest

from app.workers.celery_app import celery_app


def test_sem_agendamento_periodico() -> None:
    """Sincronização é sob demanda (spec §3.3-A): nada roda sozinho no Beat."""
    assert celery_app.conf.beat_schedule == {}


def test_nao_paraleliza_dentro_da_empresa() -> None:
    """Spec §9: paralelizar por empresa, nunca por NSU dentro da mesma."""
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_tarefa_so_sai_da_fila_quando_termina() -> None:
    """Sem acks_late, queda do worker perde a sincronização em silêncio."""
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True


def test_tarefa_bloqueada_falha_alto_em_vez_de_fingir() -> None:
    from app.workers.tarefas import sincronizar_empresa_task

    with pytest.raises(NotImplementedError, match="protocolo agente"):
        sincronizar_empresa_task("qualquer")
