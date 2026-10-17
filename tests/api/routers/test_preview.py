from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models.transaction import Direction

from .conftest import make_transaction


def test_preview_returns_matching_transactions(
    client: TestClient, db_session: Session, account_id: int, planned_item_id: int
) -> None:
    db_session.add(
        make_transaction(
            account_id,
            suffix="match",
            description="ALUGUEL IMOB XYZ",
            amount="1500.00",
            direction=Direction.OUT,
            day=5,
        )
    )
    db_session.add(
        make_transaction(
            account_id,
            suffix="nomatch",
            description="MERCADO ABC",
            amount="200.00",
            direction=Direction.OUT,
            day=6,
        )
    )
    db_session.flush()

    response = client.post(
        f"/api/planned-items/{planned_item_id}/rules/preview",
        json={"match_type": "CONTAINS", "pattern": "aluguel"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["matched_count"] == 1
    assert body["matches"][0]["description"] == "ALUGUEL IMOB XYZ"
    assert body["matches"][0]["period"] == "2026-03"
    assert body["matches"][0]["amount_abs"] == "1500.00"


def test_preview_ignores_transactions_outside_pattern(
    client: TestClient, db_session: Session, account_id: int, planned_item_id: int
) -> None:
    db_session.add(
        make_transaction(
            account_id,
            suffix="nomatch",
            description="MERCADO ABC",
            amount="200.00",
            direction=Direction.OUT,
            day=6,
        )
    )
    db_session.flush()

    response = client.post(
        f"/api/planned-items/{planned_item_id}/rules/preview",
        json={"match_type": "CONTAINS", "pattern": "aluguel"},
    )

    assert response.status_code == 200
    assert response.json() == {"matched_count": 0, "matches": []}


def test_preview_404_when_planned_item_does_not_exist(client: TestClient) -> None:
    response = client.post(
        "/api/planned-items/999999/rules/preview",
        json={"match_type": "CONTAINS", "pattern": "aluguel"},
    )
    assert response.status_code == 404


def test_preview_422_when_pattern_missing_for_contains(
    client: TestClient, planned_item_id: int
) -> None:
    response = client.post(
        f"/api/planned-items/{planned_item_id}/rules/preview",
        json={"match_type": "CONTAINS"},
    )
    assert response.status_code == 422


def test_preview_422_when_amount_range_missing_bounds(
    client: TestClient, planned_item_id: int
) -> None:
    response = client.post(
        f"/api/planned-items/{planned_item_id}/rules/preview",
        json={"match_type": "AMOUNT_RANGE", "amount_min": "100.00"},
    )
    assert response.status_code == 422
