"""Papel de aplicação sem privilégio, para a RLS valer

Revision ID: 0003_papel_aplicacao
Revises: 0002_rls

Superusuário e dono de tabela com BYPASSRLS ignoram política de RLS. Se a
aplicação conectar como o dono do schema, o isolamento multi-tenant da §8
existe só no papel — foi o que um teste pegou. Este papel é o que a API e os
workers usam; o dono fica reservado ao Alembic.
"""
from __future__ import annotations

import os

from alembic import op

from app.db.models import TABELAS_COM_RLS

revision = "0003_papel_aplicacao"
down_revision = "0002_rls"
branch_labels = None
depends_on = None

PAPEL = "nfse_app"


def upgrade() -> None:
    senha = os.environ.get("APP_DB_PASSWORD")
    if not senha:
        raise RuntimeError(
            "APP_DB_PASSWORD não definida — necessária para criar o papel de "
            "aplicação. Não há default: senha em código é vazamento."
        )
    # A senha entra por parâmetro do servidor, não por interpolação na DDL.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PAPEL}') THEN
            CREATE ROLE {PAPEL} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                   NOBYPASSRLS PASSWORD {_literal(senha)};
          ELSE
            ALTER ROLE {PAPEL} NOSUPERUSER NOBYPASSRLS PASSWORD {_literal(senha)};
          END IF;
        END $$;
        """
    )
    op.execute(f"GRANT CONNECT ON DATABASE nfse TO {PAPEL}")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {PAPEL}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {PAPEL}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {PAPEL}")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {PAPEL}"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {PAPEL}"
    )
    # audit_log não tem RLS (é transversal): a aplicação só escreve, nunca lê.
    op.execute(f"REVOKE SELECT ON audit_log FROM {PAPEL}")

    for tabela in TABELAS_COM_RLS:
        op.execute(f"ALTER TABLE {tabela} OWNER TO CURRENT_USER")


def _literal(valor: str) -> str:
    """Escapa a senha como literal SQL. Nunca é registrada em log."""
    return "'" + valor.replace("'", "''") + "'"


def downgrade() -> None:
    # ALTER DEFAULT PRIVILEGES cria dependência própria: sem revogá-la, o
    # DROP ROLE falha com DependentObjectsStillExist.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {PAPEL}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {PAPEL}"
    )
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {PAPEL}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {PAPEL}")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {PAPEL}")
    op.execute("REVOKE ALL ON DATABASE nfse FROM " + PAPEL)
    op.execute(f"DROP ROLE IF EXISTS {PAPEL}")
