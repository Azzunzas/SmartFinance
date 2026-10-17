from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.planned_items import (
    PlannedItemCreate,
    PlannedItemOut,
    PlannedItemRuleCreate,
    PlannedItemRuleOut,
    PlannedItemRuleUpdate,
    PlannedItemUpdate,
    RulePreviewMatch,
    RulePreviewRequest,
    RulePreviewResponse,
)
from core.analysis.planned_matching import PlannedKind, RuleSpec, match_planned_items
from core.repository.analysis import load_matchable_transactions
from core.repository.planned_items import (
    PlannedItemRuleValues,
    PlannedItemValues,
    create_planned_item,
    create_rule,
    delete_planned_item,
    delete_rule,
    list_planned_items,
    list_rules,
    load_planned_item,
    load_rule,
    update_planned_item,
    update_rule,
)

router = APIRouter(prefix="/api/planned-items", tags=["planned-items"])


@router.get("", response_model=list[PlannedItemOut])
def list_items(session: Session = Depends(get_session)) -> list[PlannedItemOut]:
    return [PlannedItemOut.model_validate(item) for item in list_planned_items(session)]


@router.post("", response_model=PlannedItemOut, status_code=201)
def create_item(
    body: PlannedItemCreate, session: Session = Depends(get_session)
) -> PlannedItemOut:
    values = PlannedItemValues(
        name=body.name,
        kind=body.kind,
        category_id=body.category_id,
        expected_amount=body.expected_amount,
        tolerance_pct=body.tolerance_pct,
        expected_day=body.expected_day,
        day_tolerance=body.day_tolerance,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        is_active=body.is_active,
    )
    return PlannedItemOut.model_validate(create_planned_item(session, values))


@router.get("/{planned_item_id}", response_model=PlannedItemOut)
def get_item(planned_item_id: int, session: Session = Depends(get_session)) -> PlannedItemOut:
    item = load_planned_item(session, planned_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="planned_item não encontrado")
    return PlannedItemOut.model_validate(item)


@router.patch("/{planned_item_id}", response_model=PlannedItemOut)
def patch_item(
    planned_item_id: int, body: PlannedItemUpdate, session: Session = Depends(get_session)
) -> PlannedItemOut:
    patch = body.model_dump(exclude_unset=True)
    item = update_planned_item(session, planned_item_id, patch)
    if item is None:
        raise HTTPException(status_code=404, detail="planned_item não encontrado")
    return PlannedItemOut.model_validate(item)


@router.delete("/{planned_item_id}", status_code=204)
def remove_item(planned_item_id: int, session: Session = Depends(get_session)) -> None:
    try:
        deleted = delete_planned_item(session, planned_item_id)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="não é possível remover um planned_item com matches já registrados",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="planned_item não encontrado")


@router.get("/{planned_item_id}/rules", response_model=list[PlannedItemRuleOut])
def list_item_rules(
    planned_item_id: int, session: Session = Depends(get_session)
) -> list[PlannedItemRuleOut]:
    if load_planned_item(session, planned_item_id) is None:
        raise HTTPException(status_code=404, detail="planned_item não encontrado")
    rules = list_rules(session, planned_item_id)
    return [PlannedItemRuleOut.model_validate(rule) for rule in rules]


@router.post("/{planned_item_id}/rules", response_model=PlannedItemRuleOut, status_code=201)
def create_item_rule(
    planned_item_id: int, body: PlannedItemRuleCreate, session: Session = Depends(get_session)
) -> PlannedItemRuleOut:
    if load_planned_item(session, planned_item_id) is None:
        raise HTTPException(status_code=404, detail="planned_item não encontrado")
    values = PlannedItemRuleValues(
        match_type=body.match_type,
        pattern=body.pattern,
        amount_min=body.amount_min,
        amount_max=body.amount_max,
        account_id=body.account_id,
        priority=body.priority,
    )
    return PlannedItemRuleOut.model_validate(create_rule(session, planned_item_id, values))


@router.get("/{planned_item_id}/rules/{rule_id}", response_model=PlannedItemRuleOut)
def get_item_rule(
    planned_item_id: int, rule_id: int, session: Session = Depends(get_session)
) -> PlannedItemRuleOut:
    rule = load_rule(session, rule_id)
    if rule is None or rule.planned_item_id != planned_item_id:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    return PlannedItemRuleOut.model_validate(rule)


@router.patch("/{planned_item_id}/rules/{rule_id}", response_model=PlannedItemRuleOut)
def patch_item_rule(
    planned_item_id: int,
    rule_id: int,
    body: PlannedItemRuleUpdate,
    session: Session = Depends(get_session),
) -> PlannedItemRuleOut:
    existing = load_rule(session, rule_id)
    if existing is None or existing.planned_item_id != planned_item_id:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    patch = body.model_dump(exclude_unset=True)
    updated = update_rule(session, rule_id, patch)
    assert updated is not None
    return PlannedItemRuleOut.model_validate(updated)


@router.delete("/{planned_item_id}/rules/{rule_id}", status_code=204)
def remove_item_rule(
    planned_item_id: int, rule_id: int, session: Session = Depends(get_session)
) -> None:
    existing = load_rule(session, rule_id)
    if existing is None or existing.planned_item_id != planned_item_id:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    delete_rule(session, rule_id)


@router.post("/{planned_item_id}/rules/preview", response_model=RulePreviewResponse)
def preview_rule(
    planned_item_id: int,
    body: RulePreviewRequest,
    session: Session = Depends(get_session),
) -> RulePreviewResponse:
    """Dry-run (doc §6.2): testa uma regra ainda não salva contra o
    histórico, sem gravar nada em `planned_item_rule`/`planned_item_match`."""
    planned_item = load_planned_item(session, planned_item_id)
    if planned_item is None:
        raise HTTPException(status_code=404, detail="planned_item não encontrado")

    rule = RuleSpec(
        rule_id=None,
        planned_item_id=planned_item.id,
        planned_item_kind=PlannedKind(planned_item.kind),
        valid_from=planned_item.valid_from,
        valid_to=planned_item.valid_to,
        match_type=body.match_type,
        pattern=body.pattern,
        amount_min=body.amount_min,
        amount_max=body.amount_max,
        account_id=body.account_id,
    )

    transactions = load_matchable_transactions(session)
    matches = match_planned_items(transactions, [rule])
    transactions_by_id = {t.transaction_id: t for t in transactions}

    preview_matches = [
        RulePreviewMatch(
            transaction_id=match.transaction_id,
            description=transactions_by_id[match.transaction_id].description,
            accrual_date=transactions_by_id[match.transaction_id].accrual_date,
            amount_abs=match.matched_amount,
            period=match.period,
        )
        for match in matches
    ]

    return RulePreviewResponse(matched_count=len(preview_matches), matches=preview_matches)
