from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import RecurrenceCandidate
from core.models.transaction import Direction


def _make_candidate(
    db_session: Session,
    *,
    description_norm: str = "netflix com assinatura",
    direction: Direction = Direction.OUT,
    promoted_to: int | None = None,
) -> int:
    candidate = RecurrenceCandidate(
        description_norm=description_norm,
        direction=direction,
        occurrences=4,
        avg_amount=Decimal("49.90"),
        amount_variance_pct=Decimal("0.00"),
        avg_interval_days=Decimal("30.0"),
        regularity_score=Decimal("0.987"),
        last_seen_date=date(2026, 3, 17),
        promoted_to=promoted_to,
    )
    db_session.add(candidate)
    db_session.flush()
    return candidate.id


def test_list_candidates_returns_seeded_candidate(client: TestClient, db_session: Session) -> None:
    candidate_id = _make_candidate(db_session)

    response = client.get("/api/recurrences")

    assert response.status_code == 200
    body = response.json()
    assert any(c["id"] == candidate_id for c in body)
    found = next(c for c in body if c["id"] == candidate_id)
    assert found["description_norm"] == "netflix com assinatura"
    assert found["regularity_score"] == "0.987"
    assert found["promoted_to"] is None


def test_get_candidate_returns_one_candidate(client: TestClient, db_session: Session) -> None:
    candidate_id = _make_candidate(db_session)

    response = client.get(f"/api/recurrences/{candidate_id}")

    assert response.status_code == 200
    assert response.json()["id"] == candidate_id


def test_get_candidate_returns_404(client: TestClient) -> None:
    response = client.get("/api/recurrences/999999")
    assert response.status_code == 404


def test_promote_creates_planned_item_with_rule(client: TestClient, db_session: Session) -> None:
    candidate_id = _make_candidate(db_session)

    response = client.post(
        f"/api/recurrences/{candidate_id}/promote",
        json={"name": "Netflix", "valid_from": "2026-01-01"},
    )

    assert response.status_code == 201
    item = response.json()
    assert item["name"] == "Netflix"
    assert item["kind"] == "FIXED_EXPENSE"
    assert item["expected_amount"] == "49.90"
    assert item["expected_day"] == 17  # dia do last_seen_date, já que não veio no body

    rules = client.get(f"/api/planned-items/{item['id']}/rules").json()
    assert len(rules) == 1
    assert rules[0]["match_type"] == "CONTAINS"
    assert rules[0]["pattern"] == "netflix com assinatura"

    candidates = client.get("/api/recurrences").json()
    promoted = next(c for c in candidates if c["id"] == candidate_id)
    assert promoted["promoted_to"] == item["id"]


def test_promote_income_direction_maps_to_income_kind(
    client: TestClient, db_session: Session
) -> None:
    candidate_id = _make_candidate(db_session, description_norm="salario", direction=Direction.IN)

    response = client.post(
        f"/api/recurrences/{candidate_id}/promote",
        json={"name": "Salário", "valid_from": "2026-01-01"},
    )

    assert response.status_code == 201
    assert response.json()["kind"] == "INCOME"


def test_promote_respects_explicit_expected_day(client: TestClient, db_session: Session) -> None:
    candidate_id = _make_candidate(db_session)

    response = client.post(
        f"/api/recurrences/{candidate_id}/promote",
        json={"name": "Netflix", "valid_from": "2026-01-01", "expected_day": 5},
    )

    assert response.json()["expected_day"] == 5


def test_promote_404_when_candidate_does_not_exist(client: TestClient) -> None:
    response = client.post(
        "/api/recurrences/999999/promote",
        json={"name": "X", "valid_from": "2026-01-01"},
    )
    assert response.status_code == 404


def test_promote_409_when_already_promoted(client: TestClient, db_session: Session) -> None:
    candidate_id = _make_candidate(db_session, promoted_to=None)
    first = client.post(
        f"/api/recurrences/{candidate_id}/promote",
        json={"name": "Netflix", "valid_from": "2026-01-01"},
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/recurrences/{candidate_id}/promote",
        json={"name": "Netflix de novo", "valid_from": "2026-01-01"},
    )
    assert second.status_code == 409
