from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from core.models.transaction import Direction


class RecurrenceCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description_norm: str
    direction: Direction
    occurrences: int
    avg_amount: Decimal
    amount_variance_pct: Decimal
    avg_interval_days: Decimal
    regularity_score: Decimal
    last_seen_date: date
    promoted_to: int | None
    computed_at: datetime


class RecurrencePromoteRequest(BaseModel):
    """Campos que o detector não tem como inferir sozinho: nome de exibição
    e a partir de quando o plano passa a valer (mesmo `valid_from` que a
    criação manual de `planned_item` já exige)."""

    name: str
    valid_from: date
    tolerance_pct: Decimal = Decimal("10.0")
    expected_day: int | None = None
    day_tolerance: int = 5
