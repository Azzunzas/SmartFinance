from datetime import date
from decimal import Decimal

from core.analysis.planned_matching import (
    MatchableTransaction,
    MatchType,
    PlannedItemMatch,
    PlannedKind,
    RuleSpec,
    match_planned_items,
)
from core.ingestion.normalize import normalize_description
from core.models.transaction import Direction

ACCOUNT_A = 1
ACCOUNT_B = 2

ITEM_RENT = 10
ITEM_LEISURE = 20


def _tx(
    transaction_id: int,
    *,
    account_id: int = ACCOUNT_A,
    day: int = 15,
    amount: str = "500.00",
    direction: Direction = Direction.OUT,
    description: str = "aluguel imob xyz",
    merchant_name: str | None = None,
) -> MatchableTransaction:
    return MatchableTransaction(
        transaction_id=transaction_id,
        account_id=account_id,
        accrual_date=date(2026, 3, day),
        amount_abs=Decimal(amount),
        direction=direction,
        description=description,
        description_norm=normalize_description(description),
        merchant_name=merchant_name,
    )


def _rule(
    rule_id: int | None,
    planned_item_id: int,
    *,
    kind: PlannedKind = PlannedKind.FIXED_EXPENSE,
    valid_from: date = date(2026, 1, 1),
    valid_to: date | None = None,
    match_type: MatchType = MatchType.CONTAINS,
    pattern: str | None = "aluguel",
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    account_id: int | None = None,
) -> RuleSpec:
    return RuleSpec(
        rule_id=rule_id,
        planned_item_id=planned_item_id,
        planned_item_kind=kind,
        valid_from=valid_from,
        valid_to=valid_to,
        match_type=match_type,
        pattern=pattern,
        amount_min=amount_min,
        amount_max=amount_max,
        account_id=account_id,
    )


def test_contains_matches_after_normalization() -> None:
    transactions = [_tx(1, description="ALUGUEL IMOB XYZ")]
    rules = [_rule(1, ITEM_RENT, match_type=MatchType.CONTAINS, pattern="Aluguel")]
    matches = match_planned_items(transactions, rules)
    assert matches == [
        PlannedItemMatch(
            planned_item_id=ITEM_RENT,
            transaction_id=1,
            period="2026-03",
            matched_amount=Decimal("500.00"),
            rule_id=1,
        )
    ]


def test_regex_matches_against_normalized_description() -> None:
    transactions = [_tx(1, description="Netflix.com assinatura")]
    rules = [_rule(1, ITEM_LEISURE, match_type=MatchType.REGEX, pattern=r"^netflix")]
    assert len(match_planned_items(transactions, rules)) == 1


def test_merchant_requires_exact_normalized_match() -> None:
    transactions = [_tx(1, description="compra", merchant_name="Spotify")]
    rules = [_rule(1, ITEM_LEISURE, match_type=MatchType.MERCHANT, pattern="spotify")]
    assert len(match_planned_items(transactions, rules)) == 1


def test_merchant_does_not_match_as_substring() -> None:
    transactions = [_tx(1, description="compra", merchant_name="Spotify Brasil")]
    rules = [_rule(1, ITEM_LEISURE, match_type=MatchType.MERCHANT, pattern="spotify")]
    assert match_planned_items(transactions, rules) == []


def test_amount_range_matches_within_bounds() -> None:
    transactions = [_tx(1, amount="150.00", description="mercado")]
    rules = [
        _rule(
            1,
            ITEM_LEISURE,
            match_type=MatchType.AMOUNT_RANGE,
            amount_min=Decimal("100.00"),
            amount_max=Decimal("200.00"),
        )
    ]
    assert len(match_planned_items(transactions, rules)) == 1


def test_amount_range_excludes_outside_bounds() -> None:
    transactions = [_tx(1, amount="250.00", description="mercado")]
    rules = [
        _rule(
            1,
            ITEM_LEISURE,
            match_type=MatchType.AMOUNT_RANGE,
            amount_min=Decimal("100.00"),
            amount_max=Decimal("200.00"),
        )
    ]
    assert match_planned_items(transactions, rules) == []


def test_transaction_before_valid_from_is_excluded() -> None:
    transactions = [_tx(1, day=15)]
    rules = [_rule(1, ITEM_RENT, valid_from=date(2026, 3, 20))]
    assert match_planned_items(transactions, rules) == []


def test_transaction_after_valid_to_is_excluded() -> None:
    transactions = [_tx(1, day=15)]
    rules = [_rule(1, ITEM_RENT, valid_to=date(2026, 2, 28))]
    assert match_planned_items(transactions, rules) == []


def test_income_rule_does_not_match_out_transaction() -> None:
    transactions = [_tx(1, direction=Direction.OUT, description="salario empresa xyz")]
    rules = [_rule(1, ITEM_RENT, kind=PlannedKind.INCOME, pattern="salario")]
    assert match_planned_items(transactions, rules) == []


def test_income_rule_matches_in_transaction() -> None:
    transactions = [_tx(1, direction=Direction.IN, description="salario empresa xyz")]
    rules = [_rule(1, ITEM_RENT, kind=PlannedKind.INCOME, pattern="salario")]
    assert len(match_planned_items(transactions, rules)) == 1


def test_rule_scoped_to_account_ignores_other_accounts() -> None:
    transactions = [_tx(1, account_id=ACCOUNT_B)]
    rules = [_rule(1, ITEM_RENT, account_id=ACCOUNT_A)]
    assert match_planned_items(transactions, rules) == []


def test_same_item_matched_by_two_rules_produces_a_single_row() -> None:
    transactions = [_tx(1, description="aluguel imob xyz")]
    rules = [
        _rule(1, ITEM_RENT, match_type=MatchType.CONTAINS, pattern="aluguel"),
        _rule(
            2,
            ITEM_RENT,
            match_type=MatchType.AMOUNT_RANGE,
            amount_min=Decimal("0"),
            amount_max=Decimal("1000"),
        ),
    ]
    matches = match_planned_items(transactions, rules)
    assert len(matches) == 1
    assert matches[0].rule_id == 1  # menor rule_id vence, determinístico


def test_same_transaction_can_match_two_different_items() -> None:
    # decisão de 2026-08-17: sem exclusividade entre planned_items.
    transactions = [_tx(1, description="aluguel imob xyz")]
    rules = [
        _rule(1, ITEM_RENT, match_type=MatchType.CONTAINS, pattern="aluguel"),
        _rule(
            2,
            ITEM_LEISURE,
            match_type=MatchType.AMOUNT_RANGE,
            amount_min=Decimal("0"),
            amount_max=Decimal("1000"),
        ),
    ]
    matches = match_planned_items(transactions, rules)
    matched_items = {m.planned_item_id for m in matches}
    assert matched_items == {ITEM_RENT, ITEM_LEISURE}


def test_preview_rule_without_id_is_evaluated_last_but_still_matches() -> None:
    transactions = [_tx(1, description="aluguel imob xyz")]
    rules = [_rule(None, ITEM_RENT, match_type=MatchType.CONTAINS, pattern="aluguel")]
    matches = match_planned_items(transactions, rules)
    assert len(matches) == 1
    assert matches[0].rule_id is None


def test_is_deterministic_across_repeated_runs() -> None:
    transactions = [_tx(1, description="aluguel imob xyz")]
    rules = [
        _rule(2, ITEM_RENT, match_type=MatchType.CONTAINS, pattern="aluguel"),
        _rule(
            1,
            ITEM_RENT,
            match_type=MatchType.AMOUNT_RANGE,
            amount_min=Decimal("0"),
            amount_max=Decimal("1000"),
        ),
    ]
    first_run = match_planned_items(transactions, rules)
    second_run = match_planned_items(transactions, rules)
    assert first_run == second_run
