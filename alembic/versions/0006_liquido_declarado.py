"""Guarda o líquido e o total de retenções declarados na nota

Revision ID: 0006_liquido_declarado
Revises: 0005_remove_certificado

A nota pode destacar retenções e mesmo assim trazer líquido igual ao bruto.
Para detectar isso é preciso guardar o que a nota DECLAROU, ao lado das
retenções destacadas que já existem, e comparar — ver app/domain/liquido.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_liquido_declarado"
down_revision = "0005_remove_certificado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("nfse", sa.Column("valor_liquido_declarado", sa.Numeric(15, 2)))
    op.add_column("nfse", sa.Column("total_retencoes_declarado", sa.Numeric(15, 2)))


def downgrade() -> None:
    op.drop_column("nfse", "total_retencoes_declarado")
    op.drop_column("nfse", "valor_liquido_declarado")
