from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.planned_items import PlannedItemOut
from api.schemas.recurrences import RecurrenceCandidateOut, RecurrencePromoteRequest
from core.analysis.planned_matching import MatchType, PlannedKind
from core.models.transaction import Direction
from core.repository.planned_items import (
    PlannedItemRuleValues,
    PlannedItemValues,
    create_planned_item,
    create_rule,
)
from core.repository.recurrence import (
    list_recurrence_candidates,
    load_recurrence_candidate,
    mark_promoted,
)

router = APIRouter(prefix="/api/recurrences", tags=["recurrences"])


@router.get("", response_model=list[RecurrenceCandidateOut])
def list_candidates(session: Session = Depends(get_session)) -> list[RecurrenceCandidateOut]:
    candidates = list_recurrence_candidates(session)
    return [RecurrenceCandidateOut.model_validate(c) for c in candidates]


@router.get("/{candidate_id}", response_model=RecurrenceCandidateOut)
def get_candidate(
    candidate_id: int, session: Session = Depends(get_session)
) -> RecurrenceCandidateOut:
    candidate = load_recurrence_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidato não encontrado")
    return RecurrenceCandidateOut.model_validate(candidate)


@router.post("/{candidate_id}/promote", response_model=PlannedItemOut, status_code=201)
def promote_candidate(
    candidate_id: int,
    body: RecurrencePromoteRequest,
    session: Session = Depends(get_session),
) -> PlannedItemOut:
    """Cria o `planned_item` a partir do candidato e já registra uma
    `planned_item_rule` CONTAINS com o `description_norm` que o detector usou
    pra agrupar — o item promovido nasce com pelo menos uma regra
    funcionando, em vez de vazio."""
    candidate = load_recurrence_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidato não encontrado")
    if candidate.promoted_to is not None:
        raise HTTPException(status_code=409, detail="candidato já foi promovido")

    kind = PlannedKind.INCOME if candidate.direction is Direction.IN else PlannedKind.FIXED_EXPENSE
    expected_day = (
        body.expected_day if body.expected_day is not None else candidate.last_seen_date.day
    )

    item = create_planned_item(
        session,
        PlannedItemValues(
            name=body.name,
            kind=kind,
            category_id=None,
            expected_amount=candidate.avg_amount,
            tolerance_pct=body.tolerance_pct,
            expected_day=expected_day,
            day_tolerance=body.day_tolerance,
            valid_from=body.valid_from,
            valid_to=None,
            is_active=True,
        ),
    )
    create_rule(
        session,
        item.id,
        PlannedItemRuleValues(
            match_type=MatchType.CONTAINS,
            pattern=candidate.description_norm,
            amount_min=None,
            amount_max=None,
            account_id=None,
            priority=100,
        ),
    )
    mark_promoted(session, candidate_id, item.id)

    return PlannedItemOut.model_validate(item)
