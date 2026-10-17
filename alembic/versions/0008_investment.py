"""fase 5 - investment, investment_snapshot

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investment",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "connection_id", sa.BigInteger(), sa.ForeignKey("connection.id"), nullable=False
        ),
        sa.Column(
            "pluggy_investment_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.Text()),
        sa.Column("subtype", sa.Text()),
        sa.Column("issuer", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
    )
    op.create_table(
        "investment_snapshot",
        sa.Column(
            "investment_id",
            sa.BigInteger(),
            sa.ForeignKey("investment.id"),
            primary_key=True,
        ),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("investment_snapshot")
    op.drop_table("investment")
