from datetime import date
from decimal import Decimal

from core.analysis.upcoming import UpcomingTransaction, project_upcoming
from core.models.transaction import Direction, TxStatus

REFERENCE = date(2026, 3, 15)


def _tx(
    *,
    accrual_date: date,
    amount: str = "100.00",
    direction: Direction = Direction.OUT,
    status: TxStatus = TxStatus.PENDING,
    installment_number: int | None = None,
    installment_total: int | None = None,
) -> UpcomingTransaction:
    return UpcomingTransaction(
        accrual_date=accrual_date,
        amount_abs=Decimal(amount),
        direction=direction,
        status=status,
        installment_number=installment_number,
        installment_total=installment_total,
    )


def test_pending_transaction_counts_in_its_own_month() -> None:
    transactions = [_tx(accrual_date=date(2026, 3, 20), amount="50.00")]
    result = {
        m.period: m for m in project_upcoming(transactions, reference_date=REFERENCE, months=3)
    }
    assert result["2026-03"].pending_total == Decimal("50.00")
    assert result["2026-03"].total == Decimal("50.00")


def test_pending_income_is_ignored() -> None:
    transactions = [
        _tx(accrual_date=date(2026, 3, 20), amount="3000.00", direction=Direction.IN)
    ]
    result = project_upcoming(transactions, reference_date=REFERENCE, months=3)
    assert all(m.total == Decimal("0") for m in result)


def test_installment_projects_remaining_months() -> None:
    # parcela 2 de 5, comprada em 15/03 -> faltam 3 (abr, mai, jun)
    transactions = [
        _tx(
            accrual_date=date(2026, 3, 15),
            amount="200.00",
            status=TxStatus.POSTED,
            installment_number=2,
            installment_total=5,
        )
    ]
    result = {
        m.period: m for m in project_upcoming(transactions, reference_date=REFERENCE, months=4)
    }
    assert result["2026-03"].installments_total == Decimal("0")  # parcela atual não se projeta
    assert result["2026-04"].installments_total == Decimal("200.00")
    assert result["2026-05"].installments_total == Decimal("200.00")
    assert result["2026-06"].installments_total == Decimal("200.00")


def test_last_installment_projects_nothing() -> None:
    transactions = [
        _tx(
            accrual_date=date(2026, 3, 15),
            status=TxStatus.POSTED,
            installment_number=5,
            installment_total=5,
        )
    ]
    result = project_upcoming(transactions, reference_date=REFERENCE, months=3)
    assert all(m.installments_total == Decimal("0") for m in result)


def test_non_installment_posted_transaction_is_ignored() -> None:
    transactions = [_tx(accrual_date=date(2026, 3, 15), status=TxStatus.POSTED)]
    result = project_upcoming(transactions, reference_date=REFERENCE, months=3)
    assert all(m.total == Decimal("0") for m in result)


def test_projection_beyond_the_requested_horizon_is_dropped() -> None:
    transactions = [
        _tx(
            accrual_date=date(2026, 3, 15),
            amount="200.00",
            status=TxStatus.POSTED,
            installment_number=1,
            installment_total=12,
        )
    ]
    result = project_upcoming(transactions, reference_date=REFERENCE, months=2)
    assert len(result) == 2
    assert sum((m.installments_total for m in result), Decimal(0)) == Decimal("200.00")


def test_pending_and_installments_combine_in_the_same_month() -> None:
    transactions = [
        _tx(accrual_date=date(2026, 4, 5), amount="30.00", status=TxStatus.PENDING),
        _tx(
            accrual_date=date(2026, 3, 5),
            amount="70.00",
            status=TxStatus.POSTED,
            installment_number=1,
            installment_total=2,
        ),
    ]
    result = {
        m.period: m for m in project_upcoming(transactions, reference_date=REFERENCE, months=2)
    }
    assert result["2026-04"].pending_total == Decimal("30.00")
    assert result["2026-04"].installments_total == Decimal("70.00")
    assert result["2026-04"].total == Decimal("100.00")


def test_result_covers_every_month_in_the_horizon_even_without_data() -> None:
    result = project_upcoming([], reference_date=REFERENCE, months=6)
    assert [m.period for m in result] == [
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
    ]
