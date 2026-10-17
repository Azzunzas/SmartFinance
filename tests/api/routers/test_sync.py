from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy.orm import Session

from core.models import SyncRun


def test_run_accepts_and_executes_background_task(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    executed: list[bool] = []
    monkeypatch.setattr("api.routers.sync.claim_manual_sync", lambda: True)
    monkeypatch.setattr("api.routers.sync.run_claimed_manual_sync", lambda: executed.append(True))

    response = client.post("/api/sync/run")

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert executed == [True]


def test_run_rejects_concurrent_execution(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("api.routers.sync.claim_manual_sync", lambda: False)

    response = client.post("/api/sync/run")

    assert response.status_code == 409


def test_status_reports_running_state(client: TestClient, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("api.routers.sync.manual_sync_running", lambda: True)

    response = client.get("/api/sync/status")

    assert response.status_code == 200
    assert response.json() == {"running": True}


def test_list_runs_returns_most_recent_first(client: TestClient, db_session: Session) -> None:
    db_session.add_all(
        [
            SyncRun(
                kind="INCREMENTAL",
                started_at=datetime(2026, 8, 22, tzinfo=UTC),
                status="SUCCESS",
            ),
            SyncRun(
                kind="FULL",
                started_at=datetime(2026, 8, 23, tzinfo=UTC),
                status="FAILED",
                error_message="falha controlada",
            ),
        ]
    )
    db_session.flush()

    response = client.get("/api/sync/runs", params={"limit": 2})

    assert response.status_code == 200
    assert [run["kind"] for run in response.json()] == ["FULL", "INCREMENTAL"]


def test_list_runs_filters_by_kind(client: TestClient, db_session: Session) -> None:
    db_session.add_all(
        [
            SyncRun(kind="INCREMENTAL", status="SUCCESS"),
            SyncRun(kind="MANUAL", status="PARTIAL"),
        ]
    )
    db_session.flush()

    response = client.get("/api/sync/runs", params={"kind": "MANUAL"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["kind"] == "MANUAL"
    assert response.json()[0]["status"] == "PARTIAL"
