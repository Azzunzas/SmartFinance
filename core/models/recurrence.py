from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base
from core.models.transaction import Direction

_tx_direction = sa.Enum(Direction, name="tx_direction", create_type=False)


class RecurrenceCandidate(Base):
    __tablename__ = "recurrence_candidate"
    __table_args__ = (
        sa.UniqueConstraint("description_norm", "direction", name="ux_recurrence_group"),
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    description_norm: Mapped[str] = mapped_column(sa.Text)
    direction: Mapped[Direction] = mapped_column(_tx_direction)
    occurrences: Mapped[int] = mapped_column(sa.SmallInteger)
    avg_amount: Mapped[Decimal] = mapped_column(sa.Numeric(14, 2))
    amount_variance_pct: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2))
    avg_interval_days: Mapped[Decimal] = mapped_column(sa.Numeric(5, 1))
    regularity_score: Mapped[Decimal] = mapped_column(sa.Numeric(4, 3))
    last_seen_date: Mapped[date] = mapped_column(sa.Date)
    promoted_to: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("planned_item.id", ondelete="SET NULL")
    )
    computed_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
