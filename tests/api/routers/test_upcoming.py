import datetime as _dt
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import Account, Connection, Transaction
from core.models.transaction import Direction, TxStatus
from tests.helpers import as_instant


def _as_instant(value: _dt.date | _dt.datetime) -> _dt.datetime:
    """`transaction.occurred_at` é NOT NULL desde a migration 0014 (o
    fingerprint depende do horário). Testes que só se importam com o dia
    civil usam meia-noite UTC dele."""
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
    return _dt.datetime.combine(value, _dt.time(), tzinfo=_dt.UTC)


def _connection(session: Session) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()
    return connection.id


def _account(session: Session, connection_id: int) -> int:
    account = Account(
        connection_id=connection_id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=f"acc-fp-upcoming-{uuid.uuid4()}",
        type="BANK",
        currency_code="BRL",
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _transaction(
    session: Session,
    account_id: int,
    *,
    accrual_date: date,
    amount: str,
    status: TxStatus,
    installment_number: int | None = None,
    installment_total: int | None = None,
) -> None:
    session.add(
        Transaction(
            account_id=account_id,
            pluggy_transaction_id=uuid.uuid4(),
            fingerprint=f"tx-fp-upcoming-{uuid.uuid4()}",
            description="TESTE",
            description_norm="teste",
            amount=-Decimal(amount),
            amount_abs=Decimal(amount),
            direction=Direction.OUT,
            currency_code="BRL",
            date=accrual_date,
            occurred_at=as_instant(accrual_date),
            accrual_date=accrual_date,
            status=status,
            installment_number=installment_number,
            installment_total=installment_total,
            raw={},
        )
    )
    session.flush()


def _totals_by_period(client: TestClient, months: int = 6) -> dict[str, dict[str, str]]:
    response = client.get("/api/metrics/upcoming", params={"months": months})
    assert response.status_code == 200
    body = cast(list[dict[str, str]], response.json())
    return {row["period"]: row for row in body}


def test_upcoming_includes_pending_and_projects_installments(
    client: TestClient, db_session: Session
) -> None:
    connection_id = _connection(db_session)
    account_id = _account(db_session, connection_id)

    today = datetime.now(UTC).date()
    before = _totals_by_period(client)

    _transaction(
        db_session, account_id, accrual_date=today, amount="40.00", status=TxStatus.PENDING
    )
    _transaction(
        db_session,
        account_id,
        accrual_date=today,
        amount="150.00",
        status=TxStatus.POSTED,
        installment_number=1,
        installment_total=3,
    )

    after = _totals_by_period(client)

    current_period = today.strftime("%Y-%m")
    pending_delta = Decimal(after[current_period]["pending_total"]) - Decimal(
        before.get(current_period, {}).get("pending_total", "0")
    )
    assert pending_delta == Decimal("40.00")

    # a parcela 1 não se projeta no mês corrente, só nos dois seguintes
    installments_delta_current = Decimal(
        after[current_period]["installments_total"]
    ) - Decimal(before.get(current_period, {}).get("installments_total", "0"))
    assert installments_delta_current == Decimal("0")
