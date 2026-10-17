from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.connections import ConnectionHealthOut
from core.analysis.alerts import assess_connection_health
from core.repository.connections import load_active_connections

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionHealthOut])
def list_connections(session: Session = Depends(get_session)) -> list[ConnectionHealthOut]:
    """Doc §6.2: status e `consent_expires_at`, com os dois alertas do §8
    (`consent_expiring`, `connection_stale`) já calculados — mesma lógica do
    job `check_consent`, só que sob demanda em vez de diária."""
    connections = load_active_connections(session)
    health = assess_connection_health(connections, now=datetime.now(UTC))
    return [ConnectionHealthOut.model_validate(h) for h in health]
