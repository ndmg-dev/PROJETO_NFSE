"""Função de autenticação que roda antes de existir tenant

Revision ID: 0004_autenticar
Revises: 0003_papel_aplicacao

O login é o ovo-e-galinha da RLS: para descobrir o escritório do usuário é
preciso ler a tabela usuario, mas a política exige saber o escritório antes.

A saída NÃO é afrouxar a política — seria abrir a tabela inteira. É esta função
SECURITY DEFINER: roda com os privilégios do dono, devolve no máximo UMA linha,
buscada por e-mail exato, e expõe só o que o login precisa. Quem tem EXECUTE
não ganha nada além disso.
"""
from __future__ import annotations

from alembic import op

revision = "0004_autenticar"
down_revision = "0003_papel_aplicacao"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION autenticar(p_email text)
        RETURNS TABLE (
            id uuid, escritorio_id uuid, papel text, senha_hash text, ativo boolean
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        STABLE
        AS $$
            SELECT u.id, u.escritorio_id, u.papel, u.senha_hash, u.ativo
            FROM usuario u
            WHERE u.email = p_email
            LIMIT 1
        $$;
    """)
    # PUBLIC não executa: só o papel da aplicação.
    op.execute("REVOKE ALL ON FUNCTION autenticar(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION autenticar(text) TO nfse_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS autenticar(text)")
