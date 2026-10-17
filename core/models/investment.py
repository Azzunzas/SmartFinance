import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Investment(Base):
    __tablename__ = "investment"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    connection_id: Mapped[int] = mapped_column(sa.BigInteger, sa.ForeignKey("connection.id"))
    pluggy_investment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    name: Mapped[str] = mapped_column(sa.Text)
    type: Mapped[str | None] = mapped_column(sa.Text)
    subtype: Mapped[str | None] = mapped_column(sa.Text)
    issuer: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[str | None] = mapped_column(sa.Text)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)


class InvestmentSnapshot(Base):
    __tablename__ = "investment_snapshot"

    investment_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("investment.id"), primary_key=True
    )
    captured_at: Mapped[datetime] = mapped_column(sa.TIMESTAMP(timezone=True), primary_key=True)
    balance: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
