import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import Connection, Investment, InvestmentSnapshot


def _investment(
    session: Session,
    *,
    name: str,
    is_active: bool,
    balances: list[str],
) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()

    investment = Investment(
        connection_id=connection.id,
        pluggy_investment_id=uuid.uuid4(),
        name=name,
        type="FIXED_INCOME",
        subtype="CDB",
        issuer="Banco XP",
        status="ACTIVE" if is_active else "TOTAL_WITHDRAWAL",
        is_active=is_active,
        raw={},
    )
    session.add(investment)
    session.flush()

    for day, balance in enumerate(balances, start=1):
        session.add(
            InvestmentSnapshot(
                investment_id=investment.id,
                captured_at=datetime(2026, 1, day, tzinfo=UTC),
                balance=Decimal(balance),
            )
        )
    session.flush()
    return investment.id


def test_list_investments_returns_only_active_by_default(
    client: TestClient, db_session: Session
) -> None:
    active_id = _investment(db_session, name="CDB Ativo", is_active=True, balances=["100.00"])
    inactive_id = _investment(db_session, name="CDB Zerado", is_active=False, balances=["0.00"])

    response = client.get("/api/investments")

    assert response.status_code == 200
    ids = [i["id"] for i in response.json()]
    assert active_id in ids
    assert inactive_id not in ids


def test_list_investments_active_false_includes_inactive(
    client: TestClient, db_session: Session
) -> None:
    inactive_id = _investment(db_session, name="CDB Zerado", is_active=False, balances=["0.00"])

    response = client.get("/api/investments", params={"active": "false"})

    ids = [i["id"] for i in response.json()]
    assert inactive_id in ids


def test_list_investments_returns_latest_snapshot_balance(
    client: TestClient, db_session: Session
) -> None:
    investment_id = _investment(
        db_session, name="CDB", is_active=True, balances=["100.00", "150.00", "200.00"]
    )

    response = client.get("/api/investments")

    found = next(i for i in response.json() if i["id"] == investment_id)
    assert found["balance"] == "200.00"
