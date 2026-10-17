from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

CONSENT_EXPIRING_WITHIN_DAYS = 30
CONNECTION_STALE_AFTER_HOURS = 48


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
    connection_id: int
    connector_name: str
    status: str
    last_updated_at: datetime | None
    consent_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConnectionHealth:
    connection_id: int
    connector_name: str
    status: str
    last_updated_at: datetime | None
    consent_expires_at: datetime | None
    consent_expiring: bool
    connection_stale: bool


def assess_connection_health(
    connections: Sequence[ConnectionSnapshot], *, now: datetime
) -> list[ConnectionHealth]:
    """Doc §8: consentimento a expirar em menos de 30 dias, conexão fora de
    `UPDATED` há mais de 48h — usando o `last_updated_at` que a própria
    Pluggy manda (quando ELA conseguiu atualizar a conexão), não "quando o
    sync rodou aqui".

    Uma conexão que nunca chegou a `UPDATED` (`last_updated_at is None`, ex.:
    travada em `WAITING_USER_INPUT` desde a criação) conta como travada
    imediatamente — não dá pra medir "há quanto tempo" sem uma data de
    referência, e esperar 48h pra avisar de algo que nunca funcionou seria
    pior que avisar cedo demais."""
    results: list[ConnectionHealth] = []
    for connection in connections:
        consent_expiring = connection.consent_expires_at is not None and (
            connection.consent_expires_at - now <= timedelta(days=CONSENT_EXPIRING_WITHIN_DAYS)
        )
        connection_stale = connection.status != "UPDATED" and (
            connection.last_updated_at is None
            or now - connection.last_updated_at > timedelta(hours=CONNECTION_STALE_AFTER_HOURS)
        )
        results.append(
            ConnectionHealth(
                connection_id=connection.connection_id,
                connector_name=connection.connector_name,
                status=connection.status,
                last_updated_at=connection.last_updated_at,
                consent_expires_at=connection.consent_expires_at,
                consent_expiring=consent_expiring,
                connection_stale=connection_stale,
            )
        )
    return results
