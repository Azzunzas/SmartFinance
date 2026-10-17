from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.analysis.planned_matching import MatchType, PlannedKind, RuleSpec
from core.analysis.planned_matching import PlannedItemMatch as MatchResult
from core.models import PlannedItem, PlannedItemRule
from core.models import PlannedItemMatch as PlannedItemMatchRow


@dataclass(frozen=True, slots=True)
class PlannedItemRecord:
    id: int
    name: str
    kind: str
    category_id: int | None
    expected_amount: Decimal
    tolerance_pct: Decimal
    expected_day: int | None
    day_tolerance: int
    valid_from: date
    valid_to: date | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class PlannedItemValues:
    name: str
    kind: str
    category_id: int | None
    expected_amount: Decimal
    tolerance_pct: Decimal
    expected_day: int | None
    day_tolerance: int
    valid_from: date
    valid_to: date | None
    is_active: bool


def _item_to_record(row: PlannedItem) -> PlannedItemRecord:
    return PlannedItemRecord(
        id=row.id,
        name=row.name,
        kind=row.kind,
        category_id=row.category_id,
        expected_amount=row.expected_amount,
        tolerance_pct=row.tolerance_pct,
        expected_day=row.expected_day,
        day_tolerance=row.day_tolerance,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        is_active=row.is_active,
    )


def list_planned_items(session: Session) -> list[PlannedItemRecord]:
    rows = session.execute(sa.select(PlannedItem).order_by(PlannedItem.id)).scalars().all()
    return [_item_to_record(row) for row in rows]


def load_planned_item(session: Session, planned_item_id: int) -> PlannedItemRecord | None:
    row = session.execute(
        sa.select(PlannedItem).where(PlannedItem.id == planned_item_id)
    ).scalar_one_or_none()
    return _item_to_record(row) if row is not None else None


def create_planned_item(session: Session, values: PlannedItemValues) -> PlannedItemRecord:
    row = session.execute(
        sa.insert(PlannedItem).values(**asdict(values)).returning(PlannedItem)
    ).scalar_one()
    return _item_to_record(row)


def update_planned_item(
    session: Session, planned_item_id: int, patch: dict[str, Any]
) -> PlannedItemRecord | None:
    if not patch:
        return load_planned_item(session, planned_item_id)
    row = session.execute(
        sa.update(PlannedItem)
        .where(PlannedItem.id == planned_item_id)
        .values(**patch)
        .returning(PlannedItem)
    ).scalar_one_or_none()
    return _item_to_record(row) if row is not None else None


def delete_planned_item(session: Session, planned_item_id: int) -> bool:
    """Levanta `IntegrityError` se já existir `planned_item_match` gravado
    pra este item (sem CASCADE de propósito — apagar um item já usado em
    matches destruiria histórico de aderência). Quem chama decide o que
    fazer com isso; esta função não sabe nada de HTTP."""
    deleted_id = session.execute(
        sa.delete(PlannedItem).where(PlannedItem.id == planned_item_id).returning(PlannedItem.id)
    ).scalar_one_or_none()
    return deleted_id is not None


@dataclass(frozen=True, slots=True)
class PlannedItemRuleRecord:
    id: int
    planned_item_id: int
    match_type: str
    pattern: str | None
    amount_min: Decimal | None
    amount_max: Decimal | None
    account_id: int | None
    priority: int


@dataclass(frozen=True, slots=True)
class PlannedItemRuleValues:
    match_type: str
    pattern: str | None
    amount_min: Decimal | None
    amount_max: Decimal | None
    account_id: int | None
    priority: int


def _rule_to_record(row: PlannedItemRule) -> PlannedItemRuleRecord:
    return PlannedItemRuleRecord(
        id=row.id,
        planned_item_id=row.planned_item_id,
        match_type=row.match_type,
        pattern=row.pattern,
        amount_min=row.amount_min,
        amount_max=row.amount_max,
        account_id=row.account_id,
        priority=row.priority,
    )


def list_rules(session: Session, planned_item_id: int) -> list[PlannedItemRuleRecord]:
    rows = (
        session.execute(
            sa.select(PlannedItemRule)
            .where(PlannedItemRule.planned_item_id == planned_item_id)
            .order_by(PlannedItemRule.priority, PlannedItemRule.id)
        )
        .scalars()
        .all()
    )
    return [_rule_to_record(row) for row in rows]


def load_rule(session: Session, rule_id: int) -> PlannedItemRuleRecord | None:
    row = session.execute(
        sa.select(PlannedItemRule).where(PlannedItemRule.id == rule_id)
    ).scalar_one_or_none()
    return _rule_to_record(row) if row is not None else None


def create_rule(
    session: Session, planned_item_id: int, values: PlannedItemRuleValues
) -> PlannedItemRuleRecord:
    row = session.execute(
        sa.insert(PlannedItemRule)
        .values(planned_item_id=planned_item_id, **asdict(values))
        .returning(PlannedItemRule)
    ).scalar_one()
    return _rule_to_record(row)


def update_rule(
    session: Session, rule_id: int, patch: dict[str, Any]
) -> PlannedItemRuleRecord | None:
    if not patch:
        return load_rule(session, rule_id)
    row = session.execute(
        sa.update(PlannedItemRule)
        .where(PlannedItemRule.id == rule_id)
        .values(**patch)
        .returning(PlannedItemRule)
    ).scalar_one_or_none()
    return _rule_to_record(row) if row is not None else None


def delete_rule(session: Session, rule_id: int) -> bool:
    deleted_id = session.execute(
        sa.delete(PlannedItemRule)
        .where(PlannedItemRule.id == rule_id)
        .returning(PlannedItemRule.id)
    ).scalar_one_or_none()
    return deleted_id is not None


def list_all_rules_for_matching(session: Session) -> list[RuleSpec]:
    """Junta `planned_item_rule` com o `planned_item` dono pra montar o
    `RuleSpec` que `match_planned_items` espera — só de itens `is_active`,
    um item pausado não deveria acumular match novo."""
    rows = session.execute(
        sa.select(PlannedItemRule, PlannedItem)
        .join(PlannedItem, PlannedItem.id == PlannedItemRule.planned_item_id)
        .where(PlannedItem.is_active)
    ).all()
    return [
        RuleSpec(
            rule_id=row.PlannedItemRule.id,
            planned_item_id=row.PlannedItem.id,
            planned_item_kind=PlannedKind(row.PlannedItem.kind),
            valid_from=row.PlannedItem.valid_from,
            valid_to=row.PlannedItem.valid_to,
            match_type=MatchType(row.PlannedItemRule.match_type),
            pattern=row.PlannedItemRule.pattern,
            amount_min=row.PlannedItemRule.amount_min,
            amount_max=row.PlannedItemRule.amount_max,
            account_id=row.PlannedItemRule.account_id,
        )
        for row in rows
    ]


def replace_planned_item_matches(session: Session, matches: list[MatchResult]) -> int:
    """Recompute do zero, mesmo raciocínio de `upsert_recurrence_candidates`:
    apaga tudo e insere de novo a cada rodada do job de análise — pra um
    usuário só, mais simples e barato do que rastrear o que mudou desde a
    última vez (mesmo comentário de `run_analysis`)."""
    session.execute(sa.delete(PlannedItemMatchRow))
    if not matches:
        return 0
    session.execute(
        sa.insert(PlannedItemMatchRow),
        [
            {
                "planned_item_id": m.planned_item_id,
                "period": m.period,
                "transaction_id": m.transaction_id,
                "matched_amount": m.matched_amount,
                "source": "AUTO",
            }
            for m in matches
        ],
    )
    return len(matches)
