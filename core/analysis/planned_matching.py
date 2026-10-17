import enum
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from core.ingestion.normalize import normalize_description
from core.models.transaction import Direction


class MatchType(enum.StrEnum):
    CONTAINS = "CONTAINS"
    REGEX = "REGEX"
    MERCHANT = "MERCHANT"
    AMOUNT_RANGE = "AMOUNT_RANGE"


class PlannedKind(enum.StrEnum):
    FIXED_EXPENSE = "FIXED_EXPENSE"
    INCOME = "INCOME"
    VARIABLE_BUDGET = "VARIABLE_BUDGET"


@dataclass(frozen=True, slots=True)
class MatchableTransaction:
    """Pré-requisito de quem chama, igual ao `TransferCandidate`: só passe
    transações que já passaram pelo filtro de "gasto de verdade" — POSTED,
    sem is_internal_transfer/is_card_payment/exclude_from_analysis (mesmo
    predicado da mv_monthly_cashflow). Esta função não sabe nada sobre
    classification, de propósito."""

    transaction_id: int
    account_id: int
    accrual_date: date
    amount_abs: Decimal
    direction: Direction
    description: str
    description_norm: str
    merchant_name: str | None


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """`rule_id=None` identifica a regra ainda não salva do endpoint de
    preview — é o que permite reusar esta função tanto no recompute quanto
    no dry-run. `valid_from`/`valid_to` vêm do `planned_item` dono da regra,
    não da regra em si.

    Sem `priority`, de propósito: sem exclusividade entre planned_items (uma
    transação pode contar pra mais de um ao mesmo tempo — decisão de
    2026-08-17), a coluna não tem função no matching hoje. Ela continua
    existindo no schema para quando a hierarquia de subcategorias existir."""

    rule_id: int | None
    planned_item_id: int
    planned_item_kind: PlannedKind
    valid_from: date
    valid_to: date | None
    match_type: MatchType
    pattern: str | None
    amount_min: Decimal | None
    amount_max: Decimal | None
    account_id: int | None


@dataclass(frozen=True, slots=True)
class PlannedItemMatch:
    """`rule_id` é só pra explicar o match (útil no preview); a tabela
    `planned_item_match` não tem essa coluna — quem persistir descarta."""

    planned_item_id: int
    transaction_id: int
    period: str
    matched_amount: Decimal
    rule_id: int | None


def match_planned_items(
    transactions: Sequence[MatchableTransaction],
    rules: Sequence[RuleSpec],
) -> list[PlannedItemMatch]:
    """Casa cada transação contra as regras de cada planned_item.

    Determinístico de propósito (regras ordenadas por `rule_id` antes de
    testar, `None` — o candidato do preview — por último): rodar duas vezes
    com o mesmo conjunto produz sempre o mesmo resultado, independente da
    ordem em que quem chama montou a lista."""
    sorted_rules = sorted(rules, key=lambda r: (r.rule_id is None, r.rule_id or 0))

    matches: list[PlannedItemMatch] = []
    for transaction in transactions:
        matched_items: set[int] = set()
        for rule in sorted_rules:
            if rule.planned_item_id in matched_items:
                continue
            if not _rule_applies(transaction, rule):
                continue

            matched_items.add(rule.planned_item_id)
            matches.append(
                PlannedItemMatch(
                    planned_item_id=rule.planned_item_id,
                    transaction_id=transaction.transaction_id,
                    period=transaction.accrual_date.strftime("%Y-%m"),
                    matched_amount=transaction.amount_abs,
                    rule_id=rule.rule_id,
                )
            )

    return matches


def _rule_applies(transaction: MatchableTransaction, rule: RuleSpec) -> bool:
    """Vigência, direção e conta primeiro (baratos, cortam a maioria dos
    casos sem olhar texto/regex); `match_type` só é testado se o resto já
    bateu."""
    if transaction.accrual_date < rule.valid_from:
        return False
    if rule.valid_to is not None and transaction.accrual_date > rule.valid_to:
        return False

    expected_direction = (
        Direction.IN if rule.planned_item_kind is PlannedKind.INCOME else Direction.OUT
    )
    if transaction.direction is not expected_direction:
        return False

    if rule.account_id is not None and rule.account_id != transaction.account_id:
        return False

    return _rule_matches(transaction, rule)


def _rule_matches(transaction: MatchableTransaction, rule: RuleSpec) -> bool:
    """Testa só o `match_type` — vigência/direção/account_id já foram
    checados em `_rule_applies`."""
    if rule.match_type is MatchType.CONTAINS:
        if rule.pattern is None:
            return False
        return normalize_description(rule.pattern) in transaction.description_norm

    if rule.match_type is MatchType.REGEX:
        if rule.pattern is None:
            return False
        return re.search(rule.pattern, transaction.description_norm) is not None

    if rule.match_type is MatchType.MERCHANT:
        if rule.pattern is None:
            return False
        merchant_norm = normalize_description(transaction.merchant_name or "")
        return merchant_norm == normalize_description(rule.pattern)

    if rule.match_type is MatchType.AMOUNT_RANGE:
        if rule.amount_min is None or rule.amount_max is None:
            return False
        return rule.amount_min <= transaction.amount_abs <= rule.amount_max

    raise ValueError(f"match_type desconhecido: {rule.match_type}")
