from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class PlannedItem(Base):
    __tablename__ = "planned_item"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(sa.Text)
    kind: Mapped[str] = mapped_column(sa.Text)
    category_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("category.id"))
    expected_amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    tolerance_pct: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), server_default="10.0")
    expected_day: Mapped[int | None] = mapped_column(sa.SmallInteger)
    day_tolerance: Mapped[int] = mapped_column(sa.SmallInteger, server_default="5")
    valid_from: Mapped[date] = mapped_column(sa.Date)
    valid_to: Mapped[date | None] = mapped_column(sa.Date)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())


class PlannedItemRule(Base):
    __tablename__ = "planned_item_rule"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    planned_item_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("planned_item.id", ondelete="CASCADE")
    )
    match_type: Mapped[str] = mapped_column(sa.Text)
    pattern: Mapped[str | None] = mapped_column(sa.Text)
    amount_min: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    amount_max: Mapped[Decimal | None] = mapped_column(sa.Numeric(14, 2))
    account_id: Mapped[int | None] = mapped_column(sa.BigInteger, sa.ForeignKey("account.id"))
    priority: Mapped[int] = mapped_column(sa.SmallInteger, server_default="100")


class PlannedItemMatch(Base):
    __tablename__ = "planned_item_match"

    planned_item_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("planned_item.id"), primary_key=True
    )
    period: Mapped[str] = mapped_column(sa.CHAR(7), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("transaction.id"), primary_key=True
    )
    matched_amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    source: Mapped[str] = mapped_column(sa.Text)
