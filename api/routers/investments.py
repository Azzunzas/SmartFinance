from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.investments import InvestmentOut
from core.repository.investments import list_investments

router = APIRouter(prefix="/api/investments", tags=["investments"])


@router.get("", response_model=list[InvestmentOut])
def list_all(
    active: bool = True, session: Session = Depends(get_session)
) -> list[InvestmentOut]:
    """Doc §6.2: `GET /api/investments?active=true` — `active` já nasce
    `True` por padrão (doc §3.2: "mantenha os inativos, nunca os exiba por
    padrão"); passe `?active=false` só quando quiser ver tudo, inativos
    inclusos."""
    investments = list_investments(session, active_only=active)
    return [InvestmentOut.model_validate(i) for i in investments]
