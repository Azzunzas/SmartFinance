"""fase 4 - recurrence_candidate

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

tx_direction = postgresql.ENUM("IN", "OUT", name="tx_direction", create_type=False)


def upgrade() -> None:
    op.create_table(
        "recurrence_candidate",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("description_norm", sa.Text(), nullable=False),
        sa.Column("direction", tx_direction, nullable=False),
        sa.Column("occurrences", sa.SmallInteger(), nullable=False),
        sa.Column("avg_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_variance_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("avg_interval_days", sa.Numeric(5, 1), nullable=False),
        sa.Column("regularity_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("last_seen_date", sa.Date(), nullable=False),
        sa.Column("promoted_to", sa.BigInteger(), sa.ForeignKey("planned_item.id")),
        sa.Column(
            "computed_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "ux_recurrence_group", "recurrence_candidate", ["description_norm", "direction"]
    )


def downgrade() -> None:
    op.drop_table("recurrence_candidate")
