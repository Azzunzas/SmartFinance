import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class CreditCardBill(Base):
    """Fatura fechada de cartão, como a Pluggy devolve em `GET /bills`.

    Não confundir com `account.balance` de uma conta CREDIT: aquilo é o limite
    usado (inclui parcelas futuras e compras adiadas), isto é o valor que vence.
    A Pluggy só devolve faturas já fechadas — compras do ciclo corrente não
    aparecem aqui até o fechamento. Ver migration 0018.
    """

    __tablename__ = "credit_card_bill"
    __table_args__ = (
        sa.Index("ix_credit_card_bill_account_due", "account_id", sa.text("due_date DESC")),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("account.id"))
    pluggy_bill_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    due_date: Mapped[date] = mapped_column(sa.Date)
    close_date: Mapped[date | None] = mapped_column(sa.Date)
    total_amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    minimum_payment: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    # Soma de `financeCharges` (juros, multa, mora, IOF) cobrados nesta fatura.
    finance_charges_total: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2), server_default="0")
    currency_code: Mapped[str] = mapped_column(sa.CHAR(3), server_default="BRL")
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
