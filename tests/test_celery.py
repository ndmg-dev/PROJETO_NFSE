"""Configuração do Celery e do agendamento (spec §3.4, §9)."""

from __future__ import annotations

import pytest

from app.workers.celery_app import celery_app


def test_agendamento_tem_as_tres_rotinas() -> None:
    assert set(celery_app.conf.beat_schedule) == {
        "sincronizar-empresas",
        "varrer-eventos",
        "alertar-certificados",
    }


def test_nao_paraleliza_dentro_da_empresa() -> None:
    """Spec §9: paralelizar por empresa, nunca por NSU dentro da mesma."""
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_tarefa_so_sai_da_fila_quando_termina() -> None:
    """Sem acks_late, queda do worker perde a sincronização em silêncio."""
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True


def test_tarefas_bloqueadas_falham_alto_em_vez_de_fingir() -> None:
    from app.workers.tarefas import sincronizar_todas

    with pytest.raises(NotImplementedError, match="contrato do ADN"):
        sincronizar_todas()
