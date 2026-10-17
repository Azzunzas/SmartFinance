import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import Account, Connection


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


def _account(session: Session, connection_id: int, *, type: str, **overrides: object) -> int:
    account = Account(
        connection_id=connection_id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=f"acc-fp-accounts-test-{uuid.uuid4()}",
        type=type,
        currency_code="BRL",
        balance=Decimal("0.00"),
        raw={},
        **overrides,
    )
    session.add(account)
    session.flush()
    return account.id


def test_list_accounts_includes_bank_and_credit_by_default(
    client: TestClient, db_session: Session
) -> None:
    connection_id = _connection(db_session)
    bank_id = _account(db_session, connection_id, type="BANK", name="Conta Teste")
    credit_id = _account(db_session, connection_id, type="CREDIT", name="Cartão Teste")

    response = client.get("/api/accounts")
    assert response.status_code == 200
    ids = {a["id"] for a in response.json()}
    assert bank_id in ids
    assert credit_id in ids


def test_list_accounts_filters_by_type(client: TestClient, db_session: Session) -> None:
    connection_id = _connection(db_session)
    bank_id = _account(db_session, connection_id, type="BANK", name="Conta Filtro")
    credit_id = _account(db_session, connection_id, type="CREDIT", name="Cartão Filtro")

    response = client.get("/api/accounts", params={"type": "CREDIT"})
    ids = {a["id"] for a in response.json()}
    assert credit_id in ids
    assert bank_id not in ids


def test_list_accounts_includes_card_detail_fields(
    client: TestClient, db_session: Session
) -> None:
    connection_id = _connection(db_session)
    credit_id = _account(
        db_session,
        connection_id,
        type="CREDIT",
        subtype="CREDIT_CARD",
        name="Cartão Detalhado",
        number_masked="1234",
        credit_limit=Decimal("1000.00"),
        available_credit_limit=Decimal("250.00"),
        brand="MASTERCARD",
        balance_due_date=date(2026, 9, 10),
        balance_close_date=date(2026, 8, 30),
        minimum_payment=Decimal("75.00"),
    )

    response = client.get("/api/accounts", params={"type": "CREDIT"})
    found = next(a for a in response.json() if a["id"] == credit_id)

    assert found["number_masked"] == "1234"
    assert found["brand"] == "MASTERCARD"
    assert found["balance_due_date"] == "2026-09-10"
    assert found["balance_close_date"] == "2026-08-30"
    assert found["minimum_payment"] == "75.00"
    assert found["credit_limit"] == "1000.00"
    assert found["available_credit_limit"] == "250.00"
