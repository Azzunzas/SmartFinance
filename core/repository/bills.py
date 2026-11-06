import uuid
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.analysis.upcoming import UpcomingBill
from core.models import Account, CreditCardBill

_UPDATABLE_FIELDS = (
    "due_date",
    "close_date",
    "total_amount",
    "minimum_payment",
    "finance_charges_total",
    "currency_code",
    "raw",
)


@dataclass(frozen=True, slots=True)
class BillUpsert:
    account_id: int
    pluggy_bill_id: uuid.UUID
    due_date: date
    close_date: date | None
    total_amount: Decimal
    minimum_payment: Decimal | None
    finance_charges_total: Decimal
    currency_code: str
    raw: dict[str, Any]


def upsert_bill(session: Session, values: BillUpsert) -> int:
    """`updated_at` é renovado a cada sync de propósito: é ele que desempata
    em `_latest_per_due_month` quando a Pluggy troca o id de uma fatura."""
    payload = asdict(values)
    stmt = (
        pg_insert(CreditCardBill)
        .values(**payload)
        .on_conflict_do_update(
            index_elements=["pluggy_bill_id"],
            set_={
                **{field: payload[field] for field in _UPDATABLE_FIELDS},
                "updated_at": sa.func.now(),
            },
        )
        .returning(CreditCardBill.id)
    )
    bill_id: int = session.execute(stmt).scalar_one()
    return bill_id


def _latest_per_due_month() -> sa.Subquery:
    """Uma fatura por cartão por mês de vencimento — a mais recente vista.

    A Pluggy pode trocar o `billId` de provisório para definitivo
    (changelog de agosto de 2026), e a linha com o id antigo nunca mais é
    atualizada aqui. Sem este filtro, a mesma fatura contaria duas vezes nos
    compromissos. Cartão não tem duas faturas vencendo no mesmo mês, então o
    mês de vencimento é uma chave de negócio segura."""
    due_month = sa.func.date_trunc("month", CreditCardBill.due_date)
    return (
        sa.select(CreditCardBill)
        .distinct(CreditCardBill.account_id, due_month)
        .order_by(
            CreditCardBill.account_id,
            due_month,
            CreditCardBill.updated_at.desc(),
            CreditCardBill.id.desc(),
        )
        .subquery()
    )


@dataclass(frozen=True, slots=True)
class BillRecord:
    id: int
    account_id: int
    due_date: date
    close_date: date | None
    total_amount: Decimal
    minimum_payment: Decimal | None
    finance_charges_total: Decimal
    currency_code: str


def list_bills(
    session: Session, *, account_id: int | None = None, limit: int = 12
) -> list[BillRecord]:
    """Mais recentes primeiro (por vencimento)."""
    latest = _latest_per_due_month()
    query = sa.select(latest).order_by(latest.c.due_date.desc(), latest.c.account_id)
    if account_id is not None:
        query = query.where(latest.c.account_id == account_id)
    rows = session.execute(query.limit(limit)).all()
    return [
        BillRecord(
            id=row.id,
            account_id=row.account_id,
            due_date=row.due_date,
            close_date=row.close_date,
            total_amount=row.total_amount,
            minimum_payment=row.minimum_payment,
            finance_charges_total=row.finance_charges_total,
            currency_code=row.currency_code,
        )
        for row in rows
    ]


def load_upcoming_bills(session: Session) -> list[UpcomingBill]:
    """Todas as faturas (uma por cartão por mês) de contas incluídas na
    análise. Quem decide quais ainda vencem é `project_upcoming`."""
    latest = _latest_per_due_month()
    rows = session.execute(
        sa.select(latest.c.due_date, latest.c.total_amount)
        .join(Account, Account.id == latest.c.account_id)
        .where(Account.include_in_analysis)
    ).all()
    return [UpcomingBill(due_date=row.due_date, amount=row.total_amount) for row in rows]
