from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.accounts import AccountOut
from core.repository.accounts import list_accounts

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
def list_all(
    type: str | None = None, session: Session = Depends(get_session)
) -> list[AccountOut]:
    """Doc §6.2: `GET /api/accounts` — listagem de apoio com o detalhe que
    `OverviewOut` não carrega (number_masked, updated_at, e os campos de
    cartão: brand/balance_due_date/balance_close_date/minimum_payment).
    `?type=BANK` ou `?type=CREDIT` filtra; sem o parâmetro, lista as duas."""
    accounts = list_accounts(session, account_type=type)
    return [AccountOut.model_validate(a) for a in accounts]
