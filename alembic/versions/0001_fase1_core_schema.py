"""fase 1 - schema de ingestao

connection, account, balance_snapshot, transaction, sync_run, sync_cursor

Revision ID: 0001
Revises:
Create Date: 2026-08-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

tx_direction = postgresql.ENUM("IN", "OUT", name="tx_direction")
tx_status = postgresql.ENUM("POSTED", "PENDING", name="tx_status")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "connection",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("pluggy_item_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column("connector_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("execution_status", sa.Text()),
        sa.Column("last_updated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("consent_expires_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("superseded_by", sa.BigInteger(), sa.ForeignKey("connection.id")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
    )

    op.create_table(
        "account",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "connection_id", sa.BigInteger(), sa.ForeignKey("connection.id"), nullable=False
        ),
        sa.Column("pluggy_account_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("subtype", sa.Text()),
        sa.Column("name", sa.Text()),
        sa.Column("number_masked", sa.Text()),
        sa.Column("currency_code", sa.CHAR(3), nullable=False, server_default="BRL"),
        sa.Column("balance", sa.Numeric(14, 2)),
        sa.Column("credit_limit", sa.Numeric(14, 2)),
        sa.Column("available_credit_limit", sa.Numeric(14, 2)),
        sa.Column("is_own", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("include_in_analysis", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ix_account_fingerprint", "account", ["fingerprint"])

    op.create_table(
        "balance_snapshot",
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("account.id"), primary_key=True),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), primary_key=True),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False),
    )

    op.create_table(
        "transaction",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column(
            "pluggy_transaction_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True
        ),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("description_norm", sa.Text(), nullable=False),
        sa.Column("merchant_name", sa.Text()),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount_abs", sa.Numeric(14, 2), nullable=False),
        sa.Column("direction", tx_direction, nullable=False),
        sa.Column("currency_code", sa.CHAR(3), nullable=False, server_default="BRL"),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("accrual_date", sa.Date(), nullable=False),
        sa.Column("status", tx_status, nullable=False),
        sa.Column("installment_number", sa.SmallInteger()),
        sa.Column("installment_total", sa.SmallInteger()),
        sa.Column("pluggy_category", sa.Text()),
        sa.Column("balance_after", sa.Numeric(14, 2)),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
    )
    op.create_index("ux_transaction_fingerprint", "transaction", ["fingerprint"], unique=True)
    op.execute("CREATE INDEX ix_transaction_account_date ON transaction (account_id, date DESC)")
    op.create_index("ix_transaction_accrual", "transaction", ["accrual_date"])
    op.create_index(
        "ix_transaction_status",
        "transaction",
        ["status"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_transaction_desc_norm",
        "transaction",
        ["description_norm"],
        postgresql_using="gin",
        postgresql_ops={"description_norm": "gin_trgm_ops"},
    )

    op.create_table(
        "sync_run",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("tx_inserted", sa.Integer(), server_default="0"),
        sa.Column("tx_updated", sa.Integer(), server_default="0"),
        sa.Column("tx_duplicates", sa.Integer(), server_default="0"),
        sa.Column("error_message", sa.Text()),
    )

    op.create_table(
        "sync_cursor",
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("account.id"), primary_key=True),
        sa.Column("cursor", sa.Text()),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("sync_cursor")
    op.drop_table("sync_run")
    op.drop_index("ix_transaction_desc_norm", table_name="transaction")
    op.drop_index("ix_transaction_status", table_name="transaction")
    op.drop_index("ix_transaction_accrual", table_name="transaction")
    op.execute("DROP INDEX IF EXISTS ix_transaction_account_date")
    op.drop_index("ux_transaction_fingerprint", table_name="transaction")
    op.drop_table("transaction")
    op.drop_table("balance_snapshot")
    op.drop_index("ix_account_fingerprint", table_name="account")
    op.drop_table("account")
    op.drop_table("connection")

    tx_status.drop(op.get_bind(), checkfirst=True)
    tx_direction.drop(op.get_bind(), checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
