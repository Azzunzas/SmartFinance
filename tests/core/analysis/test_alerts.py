from datetime import UTC, datetime, timedelta

from core.analysis.alerts import ConnectionSnapshot, assess_connection_health

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def _connection(
    *,
    connection_id: int = 1,
    connector_name: str = "Nubank",
    status: str = "UPDATED",
    last_updated_at: datetime | None = NOW,
    consent_expires_at: datetime | None = NOW + timedelta(days=200),
) -> ConnectionSnapshot:
    return ConnectionSnapshot(
        connection_id=connection_id,
        connector_name=connector_name,
        status=status,
        last_updated_at=last_updated_at,
        consent_expires_at=consent_expires_at,
    )


def test_healthy_connection_has_no_alerts() -> None:
    result = assess_connection_health([_connection()], now=NOW)
    assert result[0].consent_expiring is False
    assert result[0].connection_stale is False


def test_consent_expiring_within_30_days_is_flagged() -> None:
    connection = _connection(consent_expires_at=NOW + timedelta(days=15))
    result = assess_connection_health([connection], now=NOW)
    assert result[0].consent_expiring is True


def test_consent_expiring_in_more_than_30_days_is_not_flagged() -> None:
    connection = _connection(consent_expires_at=NOW + timedelta(days=45))
    result = assess_connection_health([connection], now=NOW)
    assert result[0].consent_expiring is False


def test_already_expired_consent_is_flagged() -> None:
    connection = _connection(consent_expires_at=NOW - timedelta(days=1))
    result = assess_connection_health([connection], now=NOW)
    assert result[0].consent_expiring is True


def test_connection_without_consent_expiry_is_not_flagged() -> None:
    connection = _connection(consent_expires_at=None)
    result = assess_connection_health([connection], now=NOW)
    assert result[0].consent_expiring is False


def test_status_not_updated_but_recently_updated_is_not_stale() -> None:
    connection = _connection(status="LOGIN_ERROR", last_updated_at=NOW - timedelta(hours=10))
    result = assess_connection_health([connection], now=NOW)
    assert result[0].connection_stale is False


def test_status_not_updated_for_over_48h_is_stale() -> None:
    connection = _connection(status="LOGIN_ERROR", last_updated_at=NOW - timedelta(hours=49))
    result = assess_connection_health([connection], now=NOW)
    assert result[0].connection_stale is True


def test_status_updated_is_never_stale_regardless_of_last_updated_at() -> None:
    connection = _connection(status="UPDATED", last_updated_at=NOW - timedelta(days=30))
    result = assess_connection_health([connection], now=NOW)
    assert result[0].connection_stale is False


def test_never_updated_connection_is_stale_immediately() -> None:
    connection = _connection(status="WAITING_USER_INPUT", last_updated_at=None)
    result = assess_connection_health([connection], now=NOW)
    assert result[0].connection_stale is True


def test_evaluates_multiple_connections_independently() -> None:
    healthy = _connection(connection_id=1)
    stale = _connection(
        connection_id=2, status="OUTDATED", last_updated_at=NOW - timedelta(hours=72)
    )
    result = {r.connection_id: r for r in assess_connection_health([healthy, stale], now=NOW)}
    assert result[1].connection_stale is False
    assert result[2].connection_stale is True
