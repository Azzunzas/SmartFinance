from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.analysis.recurrence import RecurrenceCandidate
from core.models import RecurrenceCandidate as RecurrenceCandidateModel
from core.models.transaction import Direction

_UPDATABLE_FIELDS = (
    "occurrences",
    "avg_amount",
    "amount_variance_pct",
    "avg_interval_days",
    "regularity_score",
    "last_seen_date",
    "computed_at",
)


def upsert_recurrence_candidates(
    session: Session, candidates: Sequence[RecurrenceCandidate]
) -> None:
    """Upsert por `(description_norm, direction)` — o `ON CONFLICT DO UPDATE`
    nunca toca em `promoted_to`, pra não perder o vínculo de um candidato já
    promovido a `planned_item` quando o recompute rodar de novo.

    Depois, apaga os candidatos que **não** aparecem neste recompute e que
    nunca foram promovidos (`promoted_to IS NULL`) — um grupo que deixou de
    ter 3+ ocorrências (ex.: você excluiu uma transação da análise) não deve
    continuar sugerido. Um candidato já promovido nunca é apagado, mesmo que
    o grupo não qualifique mais — ele virou histórico do `planned_item`, não
    sugestão ativa."""
    for candidate in candidates:
        payload = {
            "description_norm": candidate.description_norm,
            "direction": candidate.direction,
            "occurrences": candidate.occurrences,
            "avg_amount": candidate.avg_amount,
            "amount_variance_pct": candidate.amount_variance_pct,
            "avg_interval_days": candidate.avg_interval_days,
            "regularity_score": candidate.regularity_score,
            "last_seen_date": candidate.last_seen_date,
            "computed_at": sa.func.now(),
        }
        stmt = (
            pg_insert(RecurrenceCandidateModel)
            .values(**payload)
            .on_conflict_do_update(
                index_elements=["description_norm", "direction"],
                set_={field: payload[field] for field in _UPDATABLE_FIELDS},
            )
        )
        session.execute(stmt)

    stale = sa.delete(RecurrenceCandidateModel).where(
        RecurrenceCandidateModel.promoted_to.is_(None)
    )
    current_keys = [(c.description_norm, c.direction) for c in candidates]
    if current_keys:
        stale = stale.where(
            sa.tuple_(
                RecurrenceCandidateModel.description_norm, RecurrenceCandidateModel.direction
            ).not_in(current_keys)
        )
    session.execute(stale)


@dataclass(frozen=True, slots=True)
class RecurrenceCandidateRecord:
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


def _to_record(row: RecurrenceCandidateModel) -> RecurrenceCandidateRecord:
    return RecurrenceCandidateRecord(
        id=row.id,
        description_norm=row.description_norm,
        direction=row.direction,
        occurrences=row.occurrences,
        avg_amount=row.avg_amount,
        amount_variance_pct=row.amount_variance_pct,
        avg_interval_days=row.avg_interval_days,
        regularity_score=row.regularity_score,
        last_seen_date=row.last_seen_date,
        promoted_to=row.promoted_to,
        computed_at=row.computed_at,
    )


def list_recurrence_candidates(session: Session) -> list[RecurrenceCandidateRecord]:
    rows = (
        session.execute(
            sa.select(RecurrenceCandidateModel).order_by(
                RecurrenceCandidateModel.regularity_score.desc()
            )
        )
        .scalars()
        .all()
    )
    return [_to_record(row) for row in rows]


def load_recurrence_candidate(
    session: Session, candidate_id: int
) -> RecurrenceCandidateRecord | None:
    row = session.execute(
        sa.select(RecurrenceCandidateModel).where(RecurrenceCandidateModel.id == candidate_id)
    ).scalar_one_or_none()
    return _to_record(row) if row is not None else None


def mark_promoted(session: Session, candidate_id: int, planned_item_id: int) -> None:
    session.execute(
        sa.update(RecurrenceCandidateModel)
        .where(RecurrenceCandidateModel.id == candidate_id)
        .values(promoted_to=planned_item_id)
    )
