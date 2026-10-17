from datetime import UTC, date, datetime
from decimal import Decimal

from core.ingestion.normalize import (
    compute_account_fingerprint,
    compute_transaction_fingerprint,
    mask_account_number,
    normalize_description,
    resolve_accrual_date,
    resolve_direction,
)
from core.models.transaction import Direction


def _instant(hour: int = 10, minute: int = 0) -> datetime:
    return datetime(2026, 1, 5, hour, minute, tzinfo=UTC)


def test_normalize_description_removes_accent_case_and_punctuation() -> None:
    assert normalize_description("Pádaria Dõ Zé!!  ") == "padaria do ze"


def test_normalize_description_collapses_internal_whitespace() -> None:
    assert normalize_description("UBER   *TRIP   123") == "uber trip 123"


def test_mask_account_number_keeps_last_four_digits() -> None:
    assert mask_account_number("00012345678") == "•••••••5678"


def test_mask_account_number_keeps_exact_last_four() -> None:
    assert mask_account_number("123456") == "••3456"


def test_mask_account_number_none_passthrough() -> None:
    assert mask_account_number(None) is None


def test_resolve_direction_bank_negative_is_out() -> None:
    assert resolve_direction("BANK", Decimal("-50.00")) is Direction.OUT


def test_resolve_direction_bank_positive_is_in() -> None:
    assert resolve_direction("BANK", Decimal("50.00")) is Direction.IN


def test_resolve_direction_credit_purchase_positive_is_out() -> None:
    assert resolve_direction("CREDIT", Decimal("75.00")) is Direction.OUT


def test_resolve_direction_credit_payment_negative_is_in() -> None:
    assert resolve_direction("CREDIT", Decimal("-150.00")) is Direction.IN


def test_account_fingerprint_stable_for_same_inputs() -> None:
    fp1 = compute_account_fingerprint(200, "CHECKING_ACCOUNT", "••••1234")
    fp2 = compute_account_fingerprint(200, "CHECKING_ACCOUNT", "••••1234")
    assert fp1 == fp2


def test_account_fingerprint_differs_for_different_account() -> None:
    fp1 = compute_account_fingerprint(200, "CHECKING_ACCOUNT", "••••1234")
    fp2 = compute_account_fingerprint(200, "CHECKING_ACCOUNT", "••••9999")
    assert fp1 != fp2


def test_transaction_fingerprint_stable_regardless_of_decimal_precision() -> None:
    account_fp = "abc123"
    fp1 = compute_transaction_fingerprint(
        account_fp, _instant(), Decimal("12.5"), Direction.OUT, "padaria do ze"
    )
    fp2 = compute_transaction_fingerprint(
        account_fp, _instant(), Decimal("12.50"), Direction.OUT, "padaria do ze"
    )
    assert fp1 == fp2


def test_transaction_fingerprint_differs_when_description_differs() -> None:
    account_fp = "abc123"
    fp1 = compute_transaction_fingerprint(
        account_fp, _instant(), Decimal("12.50"), Direction.OUT, "padaria do ze"
    )
    fp2 = compute_transaction_fingerprint(
        account_fp, _instant(), Decimal("12.50"), Direction.OUT, "padaria da maria"
    )
    assert fp1 != fp2


def test_resolve_accrual_date_first_installment_keeps_posted_date() -> None:
    assert resolve_accrual_date(date(2026, 3, 10), 1, 6) == date(2026, 3, 10)


def test_resolve_accrual_date_none_installment_keeps_posted_date() -> None:
    assert resolve_accrual_date(date(2026, 3, 10), None, None) == date(2026, 3, 10)


def test_resolve_accrual_date_third_installment_goes_back_two_months() -> None:
    assert resolve_accrual_date(date(2026, 3, 10), 3, 6) == date(2026, 1, 10)


def test_resolve_accrual_date_clamps_day_on_shorter_month() -> None:
    # parcela 2 postada em 31/03 -> mês anterior é fevereiro, que não tem dia 31
    assert resolve_accrual_date(date(2026, 3, 31), 2, 6) == date(2026, 2, 28)


def test_resolve_accrual_date_crosses_year_boundary() -> None:
    assert resolve_accrual_date(date(2026, 1, 15), 3, 6) == date(2025, 11, 15)


def test_transaction_fingerprint_separates_identical_transactions_same_day() -> None:
    """Regressão da migration 0014. Duas transações reais, mesmo dia, mesmo valor,
    mesma descrição genérica ("PIX recebido") — só o horário difere. Enquanto o
    fingerprint usava só a data, elas colidiam e a segunda era descartada na
    ingestão: 6 transações reais tinham sido perdidas assim,
    todas entrada de dinheiro."""
    account_fp = "abc123"
    manha = compute_transaction_fingerprint(
        account_fp, _instant(14, 10), Decimal("7.00"), Direction.IN, "pix recebido"
    )
    tarde = compute_transaction_fingerprint(
        account_fp, _instant(15, 56), Decimal("7.00"), Direction.IN, "pix recebido"
    )
    assert manha != tarde


def test_transaction_fingerprint_ignores_timezone_representation() -> None:
    """O mesmo instante escrito em fusos diferentes tem que dar o mesmo
    fingerprint — senão a Pluggy mudar o fuso da resposta duplicaria tudo."""
    from datetime import timedelta, timezone

    utc = datetime(2026, 1, 5, 15, 56, tzinfo=UTC)
    brasilia = utc.astimezone(timezone(timedelta(hours=-3)))
    args = (Decimal("7.00"), Direction.IN, "pix recebido")
    assert compute_transaction_fingerprint("abc", utc, *args) == compute_transaction_fingerprint(
        "abc", brasilia, *args
    )
