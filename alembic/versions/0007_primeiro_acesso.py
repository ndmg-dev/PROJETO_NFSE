"""Funções do primeiro acesso: já configurado? e criar escritório + admin

Revision ID: 0007_primeiro_acesso
Revises: 0006_liquido_declarado

Mesmo problema do login (migration 0004): antes de existir um escritório não há
tenant para a RLS, e a tabela usuario exige um. Em vez de afrouxar a política,
duas funções SECURITY DEFINER de escopo mínimo.

criar_primeiro_acesso() é atômica: pega um advisory lock, confirma que não há
NENHUM usuário e só então cria escritório e administrador. Dois setups
simultâneos não criam dois administradores: o segundo espera o lock, vê o
usuário do primeiro e falha com 'setup_ja_concluido'.
"""
from __future__ import annotations

from alembic import op

revision = "0007_primeiro_acesso"
down_revision = "0006_liquido_declarado"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION setup_concluido()
        RETURNS boolean
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        STABLE
        AS $$ SELECT EXISTS (SELECT 1 FROM usuario) $$;
    """)
    op.execute("""
        CREATE FUNCTION criar_primeiro_acesso(
            p_escritorio text, p_email text, p_senha_hash text
        )
        RETURNS TABLE (escritorio_id uuid, usuario_id uuid)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
        DECLARE
            v_escritorio uuid := gen_random_uuid();
            v_usuario uuid := gen_random_uuid();
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtext('nfse_primeiro_acesso'));
            IF EXISTS (SELECT 1 FROM usuario) THEN
                RAISE EXCEPTION 'setup_ja_concluido';
            END IF;
            INSERT INTO escritorio (id, nome) VALUES (v_escritorio, p_escritorio);
            INSERT INTO usuario (id, escritorio_id, email, senha_hash, papel, ativo)
            VALUES (v_usuario, v_escritorio, p_email, p_senha_hash, 'admin', true);
            RETURN QUERY SELECT v_escritorio, v_usuario;
        END
        $$;
    """)
    for assinatura in ("setup_concluido()", "criar_primeiro_acesso(text, text, text)"):
        op.execute(f"REVOKE ALL ON FUNCTION {assinatura} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {assinatura} TO nfse_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS criar_primeiro_acesso(text, text, text)")
    op.execute("DROP FUNCTION IF EXISTS setup_concluido()")
