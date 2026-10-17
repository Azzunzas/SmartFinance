from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.analysis.planned_matching import MatchableTransaction
from core.analysis.upcoming import UpcomingTransaction
from core.models import Account, Transaction, TransactionClassification
from core.models.transaction import Direction, TxStatus


@dataclass(frozen=True, slots=True)
class TransactionForAnalysis:
    transaction_id: int
    account_id: int
    is_own_account: bool
    account_type: str
    pluggy_category: str | None
    description_norm: str
    date: date
    amount_abs: Decimal
    direction: Direction


def load_transactions_for_analysis(session: Session) -> list[TransactionForAnalysis]:
    """Sem filtro de status ou include_in_analysis de propósito — classificar
    (categoria, é transferência?) é uma propriedade da transação, não uma
    decisão de agregação. Quem filtra POSTED/PENDING é a view de cashflow,
    depois."""
    rows = session.execute(
        sa.select(
            Transaction.id,
            Transaction.account_id,
            Account.is_own,
            Account.type.label("account_type"),
            Transaction.pluggy_category,
            Transaction.description_norm,
            Transaction.date,
            Transaction.amount_abs,
            Transaction.direction,
        ).join(Account, Account.id == Transaction.account_id)
    ).all()
    return [
        TransactionForAnalysis(
            transaction_id=row.id,
            account_id=row.account_id,
            is_own_account=row.is_own,
            account_type=row.account_type,
            pluggy_category=row.pluggy_category,
            description_norm=row.description_norm,
            date=row.date,
            amount_abs=row.amount_abs,
            direction=row.direction,
        )
        for row in rows
    ]


def refresh_monthly_cashflow(session: Session) -> None:
    session.execute(sa.text("REFRESH MATERIALIZED VIEW mv_monthly_cashflow"))


def load_matchable_transactions(session: Session) -> list[MatchableTransaction]:
    """Mesmo predicado de "gasto de verdade" da `mv_monthly_cashflow` (doc §5):
    POSTED, conta incluída na análise, sem transferência interna, sem
    pagamento de fatura, sem exclusão manual. Compartilhado pelo matching de
    `planned_item` (preview e recompute) e pelo detector de recorrência —
    os três precisam do mesmo pool de "isso é gasto de verdade"."""
    rows = session.execute(
        sa.select(
            Transaction.id,
            Transaction.account_id,
            Transaction.accrual_date,
            Transaction.amount_abs,
            Transaction.direction,
            Transaction.description,
            Transaction.description_norm,
            Transaction.merchant_name,
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(
            TransactionClassification,
            TransactionClassification.transaction_id == Transaction.id,
        )
        .where(
            Transaction.status == TxStatus.POSTED,
            Account.include_in_analysis,
            sa.func.coalesce(TransactionClassification.is_internal_transfer, False).is_(False),
            sa.func.coalesce(TransactionClassification.is_card_payment, False).is_(False),
            sa.func.coalesce(TransactionClassification.exclude_from_analysis, False).is_(False),
        )
    ).all()
    return [
        MatchableTransaction(
            transaction_id=row.id,
            account_id=row.account_id,
            accrual_date=row.accrual_date,
            amount_abs=row.amount_abs,
            direction=row.direction,
            description=row.description,
            description_norm=row.description_norm,
            merchant_name=row.merchant_name,
        )
        for row in rows
    ]


def load_upcoming_transactions(session: Session) -> list[UpcomingTransaction]:
    """Mesmo predicado de "gasto de verdade" de `load_matchable_transactions`
    (sem transferência interna, sem pagamento de fatura, sem exclusão
    manual), mas **sem** o filtro `status == POSTED` — `project_upcoming`
    precisa tanto de `PENDING` (comprometimento imediato) quanto de `POSTED`
    com parcelas em aberto (comprometimento futuro projetado)."""
    rows = session.execute(
        sa.select(
            Transaction.accrual_date,
            Transaction.amount_abs,
            Transaction.direction,
            Transaction.status,
            Transaction.installment_number,
            Transaction.installment_total,
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(
            TransactionClassification,
            TransactionClassification.transaction_id == Transaction.id,
        )
        .where(
            Account.include_in_analysis,
            sa.func.coalesce(TransactionClassification.is_internal_transfer, False).is_(False),
            sa.func.coalesce(TransactionClassification.is_card_payment, False).is_(False),
            sa.func.coalesce(TransactionClassification.exclude_from_analysis, False).is_(False),
        )
    ).all()
    return [
        UpcomingTransaction(
            accrual_date=row.accrual_date,
            amount_abs=row.amount_abs,
            direction=row.direction,
            status=row.status,
            installment_number=row.installment_number,
            installment_total=row.installment_total,
        )
        for row in rows
    ]
