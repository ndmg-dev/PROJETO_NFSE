"""Remove a custódia central de certificado

Revision ID: 0005_remove_certificado
Revises: 0004_autenticar

Decisão de arquitetura (spec §3.3-A, 22/09/2026): o .pfx nunca sobe para o
servidor. Ele fica na estação do contador; um agente local (Java +
SunMSCAPI) o usa por lá. Esta migration desfaz a tabela `certificado` — a
RLS e o grant que a cobriam saem junto.

Reversível: o downgrade recria a tabela e a política exatamente como
estavam nas migrations 0001/0002/0003, para o caso de a decisão precisar
ser revertida.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_remove_certificado"
down_revision = "0004_autenticar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS escopo_escritorio ON certificado")
    op.execute("DROP TABLE IF EXISTS certificado")


def downgrade() -> None:
    op.create_table(
        "certificado",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "escritorio_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("escritorio.id"), nullable=False,
        ),
        sa.Column("cnpj_raiz", sa.String(8), nullable=False),
        sa.Column("pfx_ciphered", sa.LargeBinary, nullable=False),
        sa.Column("senha_ciphered", sa.LargeBinary, nullable=False),
        sa.Column("titular_cnpj", sa.String(14)),
        sa.Column("titular_nome", sa.Text),
        sa.Column("valido_de", sa.Date),
        sa.Column("valido_ate", sa.Date),
        sa.Column("ativo", sa.Boolean, server_default=sa.true()),
        sa.UniqueConstraint("escritorio_id", "cnpj_raiz", "titular_cnpj"),
    )
    op.create_index("ix_certificado_validade", "certificado", ["valido_ate"])
    op.execute("ALTER TABLE certificado ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE certificado FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY escopo_escritorio ON certificado
        USING (
          escritorio_id
          = nullif(current_setting('app.escritorio_id', true), '')::uuid
        )
        WITH CHECK (
          escritorio_id
          = nullif(current_setting('app.escritorio_id', true), '')::uuid
        )
    """)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON certificado TO nfse_app"
    )
