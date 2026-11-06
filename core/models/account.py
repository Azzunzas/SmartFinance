import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (sa.Index("ix_account_fingerprint", "fingerprint"),)

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    connection_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("connection.id"))
    pluggy_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    fingerprint: Mapped[str] = mapped_column(sa.Text)
    type: Mapped[str] = mapped_column(sa.Text)
    subtype: Mapped[str | None] = mapped_column(sa.Text)
    name: Mapped[str | None] = mapped_column(sa.Text)
    number_masked: Mapped[str | None] = mapped_column(sa.Text)
    currency_code: Mapped[str] = mapped_column(sa.CHAR(3), server_default="BRL")
    balance: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    credit_limit: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    available_credit_limit: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    brand: Mapped[str | None] = mapped_column(sa.Text)
    balance_due_date: Mapped[date | None] = mapped_column(sa.Date)
    balance_close_date: Mapped[date | None] = mapped_column(sa.Date)
    minimum_payment: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    # Parte do limite em `CREDITO_PARCELADO` (compras parceladas, "pula
    # compra") — volta em faturas futuras. Ver migration 0019.
    installment_credit_used: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    is_own: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    include_in_analysis: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshot"

    account_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("account.id"), primary_key=True
    )
    captured_at: Mapped[datetime] = mapped_column(sa.TIMESTAMP(timezone=True), primary_key=True)
    balance: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
