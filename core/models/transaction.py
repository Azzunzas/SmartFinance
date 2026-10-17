import datetime as dt
import enum
import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Direction(enum.StrEnum):
    IN = "IN"
    OUT = "OUT"


class TxStatus(enum.StrEnum):
    POSTED = "POSTED"
    PENDING = "PENDING"


# create_type=False: o tipo já existe no Postgres (criado pela migration 0001).
# Sem isso, o SQLAlchemy tentaria criar o ENUM de novo em qualquer create_all/autogenerate.
_tx_direction = sa.Enum(Direction, name="tx_direction", create_type=False)
_tx_status = sa.Enum(TxStatus, name="tx_status", create_type=False)


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        sa.Index("ux_transaction_fingerprint", "fingerprint", unique=True),
        sa.Index("ix_transaction_account_date", "account_id", sa.text("date DESC")),
        sa.Index("ix_transaction_accrual", "accrual_date"),
        sa.Index(
            "ix_transaction_status",
            "status",
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
        sa.Index(
            "ix_transaction_payment_method",
            "payment_method",
            postgresql_where=sa.text("payment_method IS NOT NULL"),
        ),
        sa.Index(
            "ix_transaction_desc_norm",
            "description_norm",
            postgresql_using="gin",
            postgresql_ops={"description_norm": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("account.id"))
    pluggy_transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    fingerprint: Mapped[str] = mapped_column(sa.Text)

    description: Mapped[str] = mapped_column(sa.Text)
    description_norm: Mapped[str] = mapped_column(sa.Text)
    merchant_name: Mapped[str | None] = mapped_column(sa.Text)

    amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    amount_abs: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    direction: Mapped[Direction] = mapped_column(_tx_direction)
    currency_code: Mapped[str] = mapped_column(sa.CHAR(3), server_default="BRL")

    date: Mapped[dt.date] = mapped_column(sa.Date)
    # O instante exato reportado pela Pluggy. `date` continua sendo o dia
    # civil usado pra ordenação e exibição; `occurred_at` existe porque o
    # fingerprint depende do horário (migration 0014) e a regra de domínio 5
    # diz que o Postgres é o arquivo permanente — o dado de que
    # a identidade da linha depende não pode viver só no `raw`.
    occurred_at: Mapped[dt.datetime] = mapped_column(sa.TIMESTAMP(timezone=True))
    accrual_date: Mapped[dt.date] = mapped_column(sa.Date)
    status: Mapped[TxStatus] = mapped_column(_tx_status)

    installment_number: Mapped[int | None] = mapped_column(sa.SmallInteger)
    installment_total: Mapped[int | None] = mapped_column(sa.SmallInteger)

    pluggy_category: Mapped[str | None] = mapped_column(sa.Text)
    payment_method: Mapped[str | None] = mapped_column(sa.Text)
    balance_after: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))

    first_seen_at: Mapped[dt.datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
