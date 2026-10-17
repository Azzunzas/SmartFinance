import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

from core.analysis.planned_matching import MatchableTransaction
from core.models.transaction import Direction

MIN_OCCURRENCES = 3

_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class RecurrenceCandidate:
    description_norm: str
    direction: Direction
    occurrences: int
    avg_amount: Decimal
    amount_variance_pct: Decimal
    avg_interval_days: Decimal
    regularity_score: Decimal
    last_seen_date: date


def detect_recurrence(transactions: Sequence[MatchableTransaction]) -> list[RecurrenceCandidate]:
    """Doc §4.5: agrupa por `description_norm` + `direction`; precisa de pelo
    menos 3 ocorrências pra existir intervalo suficiente (2 gaps) e a
    variância fazer sentido.

    Decisão de 2026-08-18: os critérios "~30±5 dias" e "variância ≤10%" do
    doc **não** são filtro de entrada — todo grupo com 3+ ocorrências vira
    candidato, e os dois critérios só alimentam o `regularity_score` (peso
    igual entre consistência de intervalo e de valor). O detector sugere;
    você decide olhando o score, sem casos de borda descartados em silêncio.
    """
    groups: dict[tuple[str, Direction], list[MatchableTransaction]] = {}
    for transaction in transactions:
        key = (transaction.description_norm, transaction.direction)
        groups.setdefault(key, []).append(transaction)

    candidates: list[RecurrenceCandidate] = []
    for group in groups.values():
        if len(group) < MIN_OCCURRENCES:
            continue
        candidate = _build_candidate(group)
        if candidate is not None:
            candidates.append(candidate)

    return sorted(candidates, key=lambda c: (c.description_norm, c.direction))


def _build_candidate(group: Sequence[MatchableTransaction]) -> RecurrenceCandidate | None:
    ordered = sorted(group, key=lambda t: t.accrual_date)

    intervals_days = [
        (later.accrual_date - earlier.accrual_date).days for earlier, later in pairwise(ordered)
    ]
    avg_interval_days = statistics.fmean(intervals_days)
    if avg_interval_days <= 0:
        return None  # todas as ocorrências no mesmo dia — não há intervalo pra medir

    interval_stdev = statistics.pstdev(intervals_days)
    interval_consistency = max(0.0, 1 - interval_stdev / avg_interval_days)

    amounts = [t.amount_abs for t in ordered]
    avg_amount = statistics.mean(amounts)
    amount_stdev = statistics.pstdev(amounts)
    amount_variance_pct = (amount_stdev / avg_amount * 100) if avg_amount > 0 else Decimal(0)
    amount_consistency = max(0.0, 1 - float(amount_variance_pct) / 100)

    regularity_score = (interval_consistency + amount_consistency) / 2

    return RecurrenceCandidate(
        description_norm=ordered[0].description_norm,
        direction=ordered[0].direction,
        occurrences=len(ordered),
        avg_amount=avg_amount.quantize(_CENTS),
        amount_variance_pct=amount_variance_pct.quantize(_CENTS),
        avg_interval_days=Decimal(str(round(avg_interval_days, 1))),
        regularity_score=Decimal(str(round(regularity_score, 3))),
        last_seen_date=ordered[-1].accrual_date,
    )
