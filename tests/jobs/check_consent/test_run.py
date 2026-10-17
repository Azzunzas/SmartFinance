import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from core.models import Connection
from jobs.check_consent.run import run_check_consent

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _connection(
    session: Session,
    *,
    status: str = "UPDATED",
    last_updated_at: datetime | None = NOW,
    consent_expires_at: datetime | None = NOW + timedelta(days=200),
    is_active: bool = True,
) -> int:
    # connector_name propositalmente genérico ("TesteConector") — os nomes
    # reais (Nubank/PicPay/Santander) já existem no banco de dev, e usá-los
    # aqui faria o teste colidir com dado real e ficar flaky.
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


def test_healthy_connection_is_not_at_risk(db_session: Session) -> None:
    connection_id = _connection(db_session)
    result = run_check_consent(db_session, now=NOW)
    assert all(c.connection_id != connection_id for c in result.at_risk)


def test_stale_connection_is_reported(db_session: Session) -> None:
    connection_id = _connection(
        db_session, status="LOGIN_ERROR", last_updated_at=NOW - timedelta(hours=72)
    )
    result = run_check_consent(db_session, now=NOW)
    at_risk = {c.connection_id: c for c in result.at_risk}
    assert at_risk[connection_id].connection_stale is True


def test_expiring_consent_is_reported(db_session: Session) -> None:
    connection_id = _connection(db_session, consent_expires_at=NOW + timedelta(days=5))
    result = run_check_consent(db_session, now=NOW)
    at_risk = {c.connection_id: c for c in result.at_risk}
    assert at_risk[connection_id].consent_expiring is True


def test_inactive_connection_is_ignored_even_if_stale(db_session: Session) -> None:
    connection_id = _connection(
        db_session,
        status="LOGIN_ERROR",
        last_updated_at=NOW - timedelta(days=30),
        is_active=False,
    )
    result = run_check_consent(db_session, now=NOW)
    assert all(c.connection_id != connection_id for c in result.at_risk)
