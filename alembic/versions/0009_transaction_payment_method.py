"""transaction.payment_method

Captura paymentData.paymentMethod da Pluggy (PIX/TED/DOC/BOLETO) — TEXT, não
enum do Postgres, mesmo padrão de account.type/transaction.pluggy_category:
evita migration se a Pluggy adicionar um valor novo amanhã.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-19

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transaction", sa.Column("payment_method", sa.Text(), nullable=True))
    op.create_index(
        "ix_transaction_payment_method",
        "transaction",
        ["payment_method"],
        postgresql_where=sa.text("payment_method IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_payment_method", table_name="transaction")
    op.drop_column("transaction", "payment_method")
