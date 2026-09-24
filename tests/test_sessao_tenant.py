"""O escopo de tenant tem de sobreviver a um commit no meio da sessão.

O checkpoint por lote da sincronização (spec §3.4) faz commit a cada lote. Como
o escopo é local à transação, sem reaplicá-lo a transação seguinte não veria
linha nenhuma e o INSERT seguinte seria recusado pela RLS.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db.base import sessao_do_escritorio


def test_escopo_sobrevive_ao_commit(cenario) -> None:  # type: ignore[no-untyped-def]
    escritorio = cenario["a"]["escritorio"]
    with sessao_do_escritorio(escritorio) as s:
        antes = s.execute(text("SELECT count(*) FROM empresa")).scalar_one()
        s.commit()
        depois = s.execute(text("SELECT count(*) FROM empresa")).scalar_one()
    assert antes == 1
    assert depois == 1, "a transação seguinte perdeu o tenant"


def test_insert_apos_commit_ainda_passa_pela_rls(cenario, engine_admin) -> None:  # type: ignore[no-untyped-def]
    escritorio = cenario["a"]["escritorio"]
    novo = uuid.uuid4()
    with sessao_do_escritorio(escritorio) as s:
        s.commit()
        s.execute(
            text("""INSERT INTO empresa (id, escritorio_id, cnpj, cnpj_raiz, razao_social,
                    ultimo_nsu, sync_ativo) VALUES (:i, :e, '11222333000181', '11222333',
                    'Depois do commit', 0, true)"""),
            {"i": novo, "e": escritorio},
        )
        s.commit()
    with engine_admin.begin() as c:
        assert c.execute(text("SELECT count(*) FROM empresa WHERE id = :i"),
                         {"i": novo}).scalar_one() == 1


def test_sessao_de_um_escritorio_nao_ve_o_outro(cenario) -> None:  # type: ignore[no-untyped-def]
    with sessao_do_escritorio(cenario["a"]["escritorio"]) as s:
        s.commit()
        ids = s.execute(text("SELECT escritorio_id FROM empresa")).scalars().all()
    assert ids == [cenario["a"]["escritorio"]]
