"""fase 3 - planned_item, planned_item_rule, planned_item_match

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-17

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planned_item",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id")),
        sa.Column("expected_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tolerance_pct", sa.Numeric(5, 2), nullable=False, server_default="10.0"),
        sa.Column("expected_day", sa.SmallInteger()),
        sa.Column("day_tolerance", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "planned_item_rule",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "planned_item_id",
            sa.BigInteger(),
            sa.ForeignKey("planned_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("pattern", sa.Text()),
        sa.Column("amount_min", sa.Numeric(14, 2)),
        sa.Column("amount_max", sa.Numeric(14, 2)),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("account.id")),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="100"),
    )

    op.create_table(
        "planned_item_match",
        sa.Column(
            "planned_item_id",
            sa.BigInteger(),
            sa.ForeignKey("planned_item.id"),
            primary_key=True,
        ),
        sa.Column("period", sa.CHAR(7), primary_key=True),
        sa.Column(
            "transaction_id",
            sa.BigInteger(),
            sa.ForeignKey("transaction.id"),
            primary_key=True,
        ),
        sa.Column("matched_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("planned_item_match")
    op.drop_table("planned_item_rule")
    op.drop_table("planned_item")
