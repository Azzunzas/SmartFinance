from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from core.analysis.alerts import ConnectionHealth, assess_connection_health
from core.repository.connections import load_active_connections


@dataclass(frozen=True, slots=True)
class CheckConsentResult:
    connections_checked: int
    at_risk: list[ConnectionHealth]


def run_check_consent(session: Session, *, now: datetime) -> CheckConsentResult:
    connections = load_active_connections(session)
    health = assess_connection_health(connections, now=now)
    at_risk = [h for h in health if h.consent_expiring or h.connection_stale]
    return CheckConsentResult(connections_checked=len(health), at_risk=at_risk)
