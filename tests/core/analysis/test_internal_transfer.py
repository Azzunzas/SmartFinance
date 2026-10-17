from datetime import date
from decimal import Decimal

from core.analysis.internal_transfer import (
    TransferCandidate,
    TransferMatch,
    is_transfer_eligible,
    match_internal_transfers,
)
from core.models.transaction import Direction

ACCOUNT_A = 1
ACCOUNT_B = 2


def _candidate(
    transaction_id: int,
    account_id: int,
    day: int,
    amount: str,
    direction: Direction,
) -> TransferCandidate:
    return TransferCandidate(
        transaction_id=transaction_id,
        account_id=account_id,
        date=date(2026, 1, day),
        amount_abs=Decimal(amount),
        direction=direction,
    )


def test_matches_out_and_in_same_day_different_accounts() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_B, 10, "500.00", Direction.IN),
    ]
    matches = match_internal_transfers(candidates)
    assert matches == [TransferMatch(out_transaction_id=1, in_transaction_id=2)]


def test_does_not_match_within_same_account() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_A, 10, "500.00", Direction.IN),
    ]
    assert match_internal_transfers(candidates) == []


def test_does_not_match_different_amounts() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_B, 10, "499.99", Direction.IN),
    ]
    assert match_internal_transfers(candidates) == []


def test_matches_at_the_edge_of_the_window() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_B, 12, "500.00", Direction.IN),  # +2 dias
    ]
    matches = match_internal_transfers(candidates, window_days=2)
    assert len(matches) == 1


def test_does_not_match_outside_the_window() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_B, 13, "500.00", Direction.IN),  # +3 dias
    ]
    assert match_internal_transfers(candidates, window_days=2) == []


def test_two_identical_pairs_are_matched_one_to_one_not_double_used() -> None:
    # o "risco conhecido" do doc §4.2 aplicado a transferência: dois pares
    # idênticos não podem colapsar num IN só sendo reusado duas vezes.
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "50.00", Direction.OUT),
        _candidate(2, ACCOUNT_A, 10, "50.00", Direction.OUT),
        _candidate(3, ACCOUNT_B, 10, "50.00", Direction.IN),
        _candidate(4, ACCOUNT_B, 10, "50.00", Direction.IN),
    ]
    matches = match_internal_transfers(candidates)
    assert len(matches) == 2
    matched_ins = {m.in_transaction_id for m in matches}
    matched_outs = {m.out_transaction_id for m in matches}
    assert matched_ins == {3, 4}
    assert matched_outs == {1, 2}


def test_unmatched_out_is_simply_excluded() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
    ]
    assert match_internal_transfers(candidates) == []


def test_picks_the_closest_date_when_multiple_candidates_match() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_B, 12, "500.00", Direction.IN),  # +2 dias
        _candidate(3, ACCOUNT_B, 11, "500.00", Direction.IN),  # +1 dia — deve ganhar
    ]
    matches = match_internal_transfers(candidates)
    assert len(matches) == 1
    assert matches[0].in_transaction_id == 3


def test_is_deterministic_across_repeated_runs() -> None:
    candidates = [
        _candidate(1, ACCOUNT_A, 10, "500.00", Direction.OUT),
        _candidate(2, ACCOUNT_A, 10, "50.00", Direction.OUT),
        _candidate(3, ACCOUNT_B, 10, "500.00", Direction.IN),
        _candidate(4, ACCOUNT_B, 10, "50.00", Direction.IN),
    ]
    first_run = match_internal_transfers(candidates)
    second_run = match_internal_transfers(candidates)
    assert first_run == second_run


def test_purchase_on_credit_card_is_never_a_transfer_candidate() -> None:
    """Regressão de 2026-08-24. Numa conta CREDIT, `OUT` é compra: o dinheiro
    vai pro comerciante, não pra outra conta sua."""
    assert not is_transfer_eligible(
        is_own_account=True, account_type="CREDIT", direction=Direction.OUT
    )


def test_card_bill_payment_leg_stays_eligible() -> None:
    """`IN` num cartão é pagamento de fatura — movimento real entre contas
    próprias, e é justamente o que o detector precisa continuar pegando."""
    assert is_transfer_eligible(is_own_account=True, account_type="CREDIT", direction=Direction.IN)


def test_bank_legs_stay_eligible_in_both_directions() -> None:
    for direction in (Direction.IN, Direction.OUT):
        assert is_transfer_eligible(is_own_account=True, account_type="BANK", direction=direction)


def test_third_party_account_is_never_eligible() -> None:
    assert not is_transfer_eligible(
        is_own_account=False, account_type="BANK", direction=Direction.OUT
    )


def test_pix_received_no_longer_pairs_with_a_same_value_card_purchase() -> None:
    """Caso real medido: um PIX de R$ 21 recebido em 12/05 casava com uma
    compra de R$ 21 no cartão em 14/05, e o par excluía a receita **e** a
    despesa das somas. Com o filtro, nenhum dos dois entra no pool — sobra um
    candidato só, e um candidato sozinho não forma par."""
    pix_recebido = TransferCandidate(
        transaction_id=634,
        account_id=3,
        date=date(2026, 5, 12),
        amount_abs=Decimal("21.00"),
        direction=Direction.IN,
    )
    compra_no_cartao = TransferCandidate(
        transaction_id=5420,
        account_id=2,
        date=date(2026, 5, 14),
        amount_abs=Decimal("21.00"),
        direction=Direction.OUT,
    )

    # Sem o filtro, os dois entram e o detector casa.
    assert match_internal_transfers([pix_recebido, compra_no_cartao]) == [
        TransferMatch(out_transaction_id=5420, in_transaction_id=634)
    ]

    # Com o filtro (o que `run_analysis` faz), a compra nem chega ao detector.
    elegiveis = [
        c
        for c, tipo in ((pix_recebido, "BANK"), (compra_no_cartao, "CREDIT"))
        if is_transfer_eligible(is_own_account=True, account_type=tipo, direction=c.direction)
    ]
    assert elegiveis == [pix_recebido]
    assert match_internal_transfers(elegiveis) == []
