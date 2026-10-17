import datetime as _dt
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import get_session, require_auth
from api.main import app
from core.models import Account, Connection, PlannedItem, Transaction
from core.models.transaction import Direction, TxStatus
from tests.helpers import as_instant


def _as_instant(value: _dt.date | _dt.datetime) -> _dt.datetime:
    """`transaction.occurred_at` é NOT NULL desde a migration 0014 (o
    fingerprint depende do horário). Testes que só se importam com o dia
    civil usam meia-noite UTC dele."""
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
    return _dt.datetime.combine(value, _dt.time(), tzinfo=_dt.UTC)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """`require_auth` sobrescrita aqui porque estes testes cobrem regra de
    negócio de cada router, não autenticação — o fluxo de login/sessão de
    verdade é testado à parte em `tests/api/routers/test_auth.py`, com um
    client próprio que não sobrescreve essa dependency."""
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[require_auth] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def account_id(db_session: Session) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()

    account = Account(
        connection_id=connection.id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint="acc-fp-preview-test",
        type="BANK",
        currency_code="BRL",
        raw={},
    )
    db_session.add(account)
    db_session.flush()
    return account.id


@pytest.fixture
def planned_item_id(db_session: Session) -> int:
    item = PlannedItem(
        name="Aluguel",
        kind="FIXED_EXPENSE",
        expected_amount=Decimal("1500.00"),
        valid_from=date(2026, 1, 1),
    )
    db_session.add(item)
    db_session.flush()
    return item.id


def make_transaction(
    account_id: int,
    *,
    suffix: str,
    description: str,
    amount: str,
    direction: Direction,
    day: int,
) -> Transaction:
    signed_amount = Decimal(amount) if direction is Direction.IN else -Decimal(amount)
    return Transaction(
        account_id=account_id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-preview-{suffix}",
        description=description,
        description_norm=description.lower(),
        amount=signed_amount,
        amount_abs=Decimal(amount),
        direction=direction,
        currency_code="BRL",
        date=date(2026, 3, day),
        occurred_at=as_instant(date(2026, 3, day)),
        accrual_date=date(2026, 3, day),
        status=TxStatus.POSTED,
        raw={},
    )
