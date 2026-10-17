import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import Connection

NOW = datetime.now(UTC)


def _connection(
    session: Session,
    *,
    status: str = "UPDATED",
    last_updated_at: datetime | None = NOW,
    consent_expires_at: datetime | None = NOW + timedelta(days=200),
    is_active: bool = True,
) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=999,
        connector_name="TesteConector",
        status=status,
        last_updated_at=last_updated_at,
        consent_expires_at=consent_expires_at,
        is_active=is_active,
        raw={},
    )
    session.add(connection)
    session.flush()
    return connection.id


def test_list_connections_includes_computed_alert_flags(
    client: TestClient, db_session: Session
) -> None:
    connection_id = _connection(
        db_session, status="LOGIN_ERROR", last_updated_at=NOW - timedelta(hours=72)
    )

    response = client.get("/api/connections")

    assert response.status_code == 200
    body = {c["connection_id"]: c for c in response.json()}
    assert body[connection_id]["connection_stale"] is True
    assert body[connection_id]["consent_expiring"] is False


def test_list_connections_excludes_inactive(client: TestClient, db_session: Session) -> None:
    connection_id = _connection(db_session, is_active=False)

    response = client.get("/api/connections")

    ids = [c["connection_id"] for c in response.json()]
    assert connection_id not in ids
