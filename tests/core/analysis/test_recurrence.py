from datetime import date, timedelta
from decimal import Decimal

from core.analysis.planned_matching import MatchableTransaction
from core.analysis.recurrence import detect_recurrence
from core.ingestion.normalize import normalize_description
from core.models.transaction import Direction

ACCOUNT_A = 1


def _tx(
    transaction_id: int,
    *,
    day_offset: int,
    amount: str,
    direction: Direction = Direction.OUT,
    description: str = "netflix.com assinatura",
) -> MatchableTransaction:
    return MatchableTransaction(
        transaction_id=transaction_id,
        account_id=ACCOUNT_A,
        accrual_date=date(2026, 1, 1) + timedelta(days=day_offset),
        amount_abs=Decimal(amount),
        direction=direction,
        description=description,
        description_norm=normalize_description(description),
        merchant_name=None,
    )


def test_group_with_fewer_than_three_occurrences_is_ignored() -> None:
    transactions = [
        _tx(1, day_offset=0, amount="49.90"),
        _tx(2, day_offset=30, amount="49.90"),
    ]
    assert detect_recurrence(transactions) == []


def test_perfectly_regular_group_scores_close_to_one() -> None:
    transactions = [
        _tx(1, day_offset=0, amount="49.90"),
        _tx(2, day_offset=30, amount="49.90"),
        _tx(3, day_offset=60, amount="49.90"),
        _tx(4, day_offset=90, amount="49.90"),
    ]
    candidates = detect_recurrence(transactions)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.occurrences == 4
    assert candidate.avg_amount == Decimal("49.90")
    assert candidate.amount_variance_pct == Decimal("0.00")
    assert candidate.avg_interval_days == Decimal("30.0")
    assert candidate.regularity_score == Decimal("1.000")
    assert candidate.last_seen_date == transactions[-1].accrual_date


def test_irregular_group_still_appears_but_with_lower_score() -> None:
    # doc §4.5 seria ~30±5, mas a decisão de 2026-08-18 foi não filtrar por
    # isso — intervalos bem irregulares ainda devem aparecer, só que com nota
    # mais baixa que um grupo perfeitamente regular, em vez de sumir em
    # silêncio.
    regular = [
        _tx(1, day_offset=0, amount="50.00", description="regular"),
        _tx(2, day_offset=30, amount="50.00", description="regular"),
        _tx(3, day_offset=60, amount="50.00", description="regular"),
        _tx(4, day_offset=90, amount="50.00", description="regular"),
    ]
    irregular = [
        _tx(5, day_offset=0, amount="50.00", description="irregular"),
        _tx(6, day_offset=12, amount="50.00", description="irregular"),
        _tx(7, day_offset=60, amount="50.00", description="irregular"),
        _tx(8, day_offset=150, amount="50.00", description="irregular"),
    ]
    candidates = {c.description_norm: c for c in detect_recurrence(regular + irregular)}
    assert len(candidates) == 2
    assert candidates["irregular"].regularity_score < candidates["regular"].regularity_score


def test_amount_variance_lowers_the_score() -> None:
    stable = [
        _tx(1, day_offset=0, amount="50.00", description="a"),
        _tx(2, day_offset=30, amount="50.00", description="a"),
        _tx(3, day_offset=60, amount="50.00", description="a"),
    ]
    variable = [
        _tx(4, day_offset=0, amount="30.00", description="b"),
        _tx(5, day_offset=30, amount="50.00", description="b"),
        _tx(6, day_offset=60, amount="70.00", description="b"),
    ]
    candidates = {c.description_norm: c for c in detect_recurrence(stable + variable)}
    assert candidates["a"].regularity_score > candidates["b"].regularity_score


def test_groups_by_description_norm_and_direction_separately() -> None:
    out_group = [
        _tx(1, day_offset=0, amount="50.00", direction=Direction.OUT, description="salario"),
        _tx(2, day_offset=30, amount="50.00", direction=Direction.OUT, description="salario"),
        _tx(3, day_offset=60, amount="50.00", direction=Direction.OUT, description="salario"),
    ]
    in_group = [
        _tx(4, day_offset=0, amount="3000.00", direction=Direction.IN, description="salario"),
        _tx(5, day_offset=30, amount="3000.00", direction=Direction.IN, description="salario"),
        _tx(6, day_offset=60, amount="3000.00", direction=Direction.IN, description="salario"),
    ]
    candidates = detect_recurrence(out_group + in_group)
    assert len(candidates) == 2
    directions = {c.direction for c in candidates}
    assert directions == {Direction.IN, Direction.OUT}


def test_same_day_occurrences_are_excluded_no_temporal_interval() -> None:
    transactions = [
        _tx(1, day_offset=0, amount="10.00"),
        _tx(2, day_offset=0, amount="10.00"),
        _tx(3, day_offset=0, amount="10.00"),
    ]
    assert detect_recurrence(transactions) == []


def test_description_is_normalized_before_grouping() -> None:
    transactions = [
        _tx(1, day_offset=0, amount="49.90", description="Netflix.com Assinatura"),
        _tx(2, day_offset=30, amount="49.90", description="NETFLIX.COM ASSINATURA"),
        _tx(3, day_offset=60, amount="49.90", description="netflix.com assinatura"),
    ]
    candidates = detect_recurrence(transactions)
    assert len(candidates) == 1
    assert candidates[0].description_norm == "netflix com assinatura"
