"""account.brand/balance_due_date/balance_close_date/minimum_payment

Expõe em colunas tipadas o que já sobrevive em account.raw desde o fix de
extra="allow" (ver migration 0009) — bandeira,
vencimento, fechamento e pagamento mínimo do cartão.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-20

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("account", sa.Column("brand", sa.Text(), nullable=True))
    op.add_column("account", sa.Column("balance_due_date", sa.Date(), nullable=True))
    op.add_column("account", sa.Column("balance_close_date", sa.Date(), nullable=True))
    op.add_column("account", sa.Column("minimum_payment", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("account", "minimum_payment")
    op.drop_column("account", "balance_close_date")
    op.drop_column("account", "balance_due_date")
    op.drop_column("account", "brand")
