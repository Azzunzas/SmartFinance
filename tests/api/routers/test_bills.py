import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import Account, Connection
from core.repository.bills import BillUpsert, upsert_bill


def _card(session: Session) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()
    account = Account(
        connection_id=connection.id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=f"acc-fp-bills-api-{uuid.uuid4()}",
        type="CREDIT",
        subtype="CREDIT_CARD",
        currency_code="BRL",
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _bill(account_id: int, due_date: date, total: str) -> BillUpsert:
    return BillUpsert(
        account_id=account_id,
        pluggy_bill_id=uuid.uuid4(),
        due_date=due_date,
        close_date=date(due_date.year, due_date.month, 4),
        total_amount=Decimal(total),
        minimum_payment=Decimal("125.88"),
        finance_charges_total=Decimal("1.66"),
        currency_code="BRL",
        raw={"payments": []},
    )


def test_list_bills_filters_by_card_most_recent_first(
    client: TestClient, db_session: Session
) -> None:
    card = _card(db_session)
    other_card = _card(db_session)
    upsert_bill(db_session, _bill(card, date(2026, 10, 10), "2382.91"))
    upsert_bill(db_session, _bill(card, date(2026, 11, 10), "2517.59"))
    upsert_bill(db_session, _bill(other_card, date(2026, 11, 10), "157.50"))

    response = client.get("/api/bills", params={"account_id": card})

    assert response.status_code == 200
    body = response.json()
    assert [b["total_amount"] for b in body] == ["2517.59", "2382.91"]
    assert body[0]["due_date"] == "2026-11-10"
    assert body[0]["close_date"] == "2026-11-04"
    assert body[0]["minimum_payment"] == "125.88"
    assert body[0]["finance_charges_total"] == "1.66"
    assert "raw" not in body[0]


def test_list_bills_rejects_limit_out_of_range(client: TestClient) -> None:
    assert client.get("/api/bills", params={"limit": 0}).status_code == 422
