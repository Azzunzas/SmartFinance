from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import PlannedItemMatch
from core.models.transaction import Direction

from .conftest import make_transaction


def test_create_and_get_planned_item(client: TestClient) -> None:
    response = client.post(
        "/api/planned-items",
        json={
            "name": "Aluguel",
            "kind": "FIXED_EXPENSE",
            "expected_amount": "1500.00",
            "valid_from": "2026-01-01",
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Aluguel"
    assert created["tolerance_pct"] == "10.00"  # default do schema, NUMERIC(5,2)

    response = client.get(f"/api/planned-items/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_create_planned_item_rejects_valid_to_before_valid_from(client: TestClient) -> None:
    response = client.post(
        "/api/planned-items",
        json={
            "name": "Aluguel",
            "kind": "FIXED_EXPENSE",
            "expected_amount": "1500.00",
            "valid_from": "2026-03-01",
            "valid_to": "2026-01-01",
        },
    )
    assert response.status_code == 422


def test_list_planned_items(client: TestClient, planned_item_id: int) -> None:
    response = client.get("/api/planned-items")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert planned_item_id in ids


def test_patch_planned_item_updates_only_given_fields(
    client: TestClient, planned_item_id: int
) -> None:
    response = client.patch(
        f"/api/planned-items/{planned_item_id}", json={"expected_amount": "1600.00"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["expected_amount"] == "1600.00"
    assert body["name"] == "Aluguel"  # não mexeu no resto


def test_patch_planned_item_404(client: TestClient) -> None:
    response = client.patch("/api/planned-items/999999", json={"expected_amount": "1.00"})
    assert response.status_code == 404


def test_delete_planned_item(client: TestClient, planned_item_id: int) -> None:
    response = client.delete(f"/api/planned-items/{planned_item_id}")
    assert response.status_code == 204
    assert client.get(f"/api/planned-items/{planned_item_id}").status_code == 404


def test_delete_planned_item_404(client: TestClient) -> None:
    response = client.delete("/api/planned-items/999999")
    assert response.status_code == 404


def test_delete_planned_item_with_existing_match_returns_409(
    client: TestClient, db_session: Session, account_id: int, planned_item_id: int
) -> None:
    transaction = make_transaction(
        account_id,
        suffix="matched",
        description="ALUGUEL IMOB XYZ",
        amount="1500.00",
        direction=Direction.OUT,
        day=5,
    )
    db_session.add(transaction)
    db_session.flush()
    db_session.add(
        PlannedItemMatch(
            planned_item_id=planned_item_id,
            period="2026-03",
            transaction_id=transaction.id,
            matched_amount=Decimal("1500.00"),
            source="AUTO",
        )
    )
    db_session.flush()

    response = client.delete(f"/api/planned-items/{planned_item_id}")
    assert response.status_code == 409


def test_create_rule_for_nonexistent_item_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/planned-items/999999/rules",
        json={"match_type": "CONTAINS", "pattern": "aluguel"},
    )
    assert response.status_code == 404


def test_rule_crud_happy_path(client: TestClient, planned_item_id: int) -> None:
    create_response = client.post(
        f"/api/planned-items/{planned_item_id}/rules",
        json={"match_type": "CONTAINS", "pattern": "aluguel", "priority": 50},
    )
    assert create_response.status_code == 201
    rule = create_response.json()
    assert rule["planned_item_id"] == planned_item_id
    assert rule["priority"] == 50

    list_response = client.get(f"/api/planned-items/{planned_item_id}/rules")
    assert list_response.status_code == 200
    assert [r["id"] for r in list_response.json()] == [rule["id"]]

    get_response = client.get(f"/api/planned-items/{planned_item_id}/rules/{rule['id']}")
    assert get_response.status_code == 200
    assert get_response.json() == rule

    patch_response = client.patch(
        f"/api/planned-items/{planned_item_id}/rules/{rule['id']}",
        json={"priority": 10},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["priority"] == 10
    assert patch_response.json()["pattern"] == "aluguel"  # não mexeu no resto

    delete_response = client.delete(f"/api/planned-items/{planned_item_id}/rules/{rule['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/planned-items/{planned_item_id}/rules/{rule['id']}").status_code == 404


def test_create_rule_rejects_contains_without_pattern(
    client: TestClient, planned_item_id: int
) -> None:
    response = client.post(
        f"/api/planned-items/{planned_item_id}/rules",
        json={"match_type": "CONTAINS"},
    )
    assert response.status_code == 422


def test_rule_belongs_to_a_different_item_returns_404(client: TestClient) -> None:
    other_item = client.post(
        "/api/planned-items",
        json={
            "name": "Internet",
            "kind": "FIXED_EXPENSE",
            "expected_amount": "100.00",
            "valid_from": date(2026, 1, 1).isoformat(),
        },
    ).json()
    other_rule = client.post(
        f"/api/planned-items/{other_item['id']}/rules",
        json={"match_type": "CONTAINS", "pattern": "internet"},
    ).json()

    another_item = client.post(
        "/api/planned-items",
        json={
            "name": "Aluguel",
            "kind": "FIXED_EXPENSE",
            "expected_amount": "1500.00",
            "valid_from": date(2026, 1, 1).isoformat(),
        },
    ).json()

    response = client.get(f"/api/planned-items/{another_item['id']}/rules/{other_rule['id']}")
    assert response.status_code == 404
