"""fase 2 - transaction_classification

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-17

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_classification",
        sa.Column(
            "transaction_id", sa.BigInteger(), sa.ForeignKey("transaction.id"), primary_key=True
        ),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id")),
        sa.Column(
            "is_internal_transfer", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("is_card_payment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "exclude_from_analysis", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("counterpart_tx_id", sa.BigInteger(), sa.ForeignKey("transaction.id")),
        sa.Column("note", sa.Text()),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("transaction_classification")
