import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from core.models.transaction import Direction, TxStatus


@dataclass(frozen=True, slots=True)
class UpcomingTransaction:
    """Pré-requisito de quem chama, igual `MatchableTransaction`: só passe
    transações já filtradas por "gasto de verdade" (sem transferência
    interna, sem pagamento de fatura) — mas, diferente de `MatchableTransaction`,
    inclua tanto POSTED quanto PENDING. É essa função que decide o que fazer
    com cada status, não quem carrega os dados."""

    accrual_date: date
    amount_abs: Decimal
    direction: Direction
    status: TxStatus
    installment_number: int | None
    installment_total: int | None


@dataclass(frozen=True, slots=True)
class MonthlyCommitment:
    period: str
    pending_total: Decimal
    installments_total: Decimal
    total: Decimal


def project_upcoming(
    transactions: Sequence[UpcomingTransaction], *, reference_date: date, months: int
) -> list[MonthlyCommitment]:
    """Doc §4.4/§5: "comprometimento futuro" = PENDING + parcelas projetadas,
    por mês, começando no mês de `reference_date` (inclusive).

    Só `direction=OUT` conta — comprometimento é o que você vai *pagar*, não
    entrada pendente. `PENDING` entra no mês da própria `accrual_date`
    (a Pluggy já informa a data esperada). Uma parcela `POSTED` com
    `installment_number < installment_total` ainda tem parcelas futuras que a
    Pluggy não mostra como linha própria — projeta uma por mês, mesmo valor,
    a partir do mês seguinte à `accrual_date` da parcela atual."""
    periods = _future_periods(reference_date, months)
    pending_by_period: dict[str, Decimal] = dict.fromkeys(periods, Decimal(0))
    installments_by_period: dict[str, Decimal] = dict.fromkeys(periods, Decimal(0))

    for transaction in transactions:
        if transaction.direction is not Direction.OUT:
            continue

        if transaction.status is TxStatus.PENDING:
            period = _period(transaction.accrual_date)
            if period in pending_by_period:
                pending_by_period[period] += transaction.amount_abs
            continue

        if (
            transaction.status is TxStatus.POSTED
            and transaction.installment_number is not None
            and transaction.installment_total is not None
            and transaction.installment_number < transaction.installment_total
        ):
            remaining = transaction.installment_total - transaction.installment_number
            for offset in range(1, remaining + 1):
                period = _period(_add_months(transaction.accrual_date, offset))
                if period in installments_by_period:
                    installments_by_period[period] += transaction.amount_abs

    return [
        MonthlyCommitment(
            period=period,
            pending_total=pending_by_period[period],
            installments_total=installments_by_period[period],
            total=pending_by_period[period] + installments_by_period[period],
        )
        for period in periods
    ]


def _future_periods(reference_date: date, months: int) -> list[str]:
    return [_period(_add_months(reference_date, offset)) for offset in range(months)]


def _period(value: date) -> str:
    return value.strftime("%Y-%m")


def _add_months(reference: date, months: int) -> date:
    month_index = reference.month - 1 + months
    year = reference.year + month_index // 12
    month = month_index % 12 + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
