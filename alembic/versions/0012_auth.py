"""app_user, app_session — autenticação single-user

Tabela `app_user` de uma linha só (usuário único do projeto, docs/regras-do-projeto.md §1)
+ `app_session` pra sessão via cookie httpOnly (doc arquitetura §6.4).
`app_session.id` é o próprio valor do cookie — token aleatório opaco, não
JWT (a doc rejeita JWT/refresh explicitamente: "complexidade sem benefício
pra um usuário só"). `user_id` na FK existe hoje sem necessidade prática
(só há um usuário possível), mas evita reescrever a tabela se o app virar
produto multi-usuário no futuro (decisão de 2026-08-21).

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-21

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "app_session",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_app_session_user_id", "app_session", ["user_id"])


def downgrade() -> None:
    op.drop_table("app_session")
    op.drop_table("app_user")
