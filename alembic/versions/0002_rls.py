"""Row-Level Security por escritório

Revision ID: 0002_rls
Revises: 0001_inicial
"""
from __future__ import annotations

from alembic import op

from app.db.models import TABELAS_COM_RLS

revision = "0002_rls"
down_revision = "0001_inicial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for tabela in TABELAS_COM_RLS:
        op.execute(f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY")
        # FORCE é o que faz a política valer também para o dono da tabela.
        # Sem isto, a aplicação (que conecta como dono) ignora a RLS em
        # silêncio e o isolamento existe só no papel.
        op.execute(f"ALTER TABLE {tabela} FORCE ROW LEVEL SECURITY")
        # nullif(...): com a variável ausente OU vazia, current_setting devolve
        # '' e ''::uuid levanta DataError, derrubando a query. Com nullif vira
        # NULL, a comparação vira NULL, e a política simplesmente não libera
        # nenhuma linha — falha fechada sem quebrar o pedido.
        op.execute(f"""
            CREATE POLICY escopo_escritorio ON {tabela}
            USING (
              escritorio_id
              = nullif(current_setting('app.escritorio_id', true), '')::uuid
            )
            WITH CHECK (
              escritorio_id
              = nullif(current_setting('app.escritorio_id', true), '')::uuid
            )
        """)


def downgrade() -> None:
    for tabela in TABELAS_COM_RLS:
        op.execute(f"DROP POLICY IF EXISTS escopo_escritorio ON {tabela}")
        op.execute(f"ALTER TABLE {tabela} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tabela} DISABLE ROW LEVEL SECURITY")
