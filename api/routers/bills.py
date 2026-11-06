from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.bills import BillOut
from core.repository.bills import list_bills

router = APIRouter(prefix="/api/bills", tags=["bills"])


@router.get("", response_model=list[BillOut])
def list_all(
    account_id: int | None = None,
    limit: int = Query(12, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[BillOut]:
    """Faturas fechadas de cartão, mais recentes primeiro (por vencimento).
    `?account_id=` filtra um cartão. Ao contrário de `account.balance` (limite
    usado), `total_amount` é o valor que de fato vence."""
    return [
        BillOut.model_validate(bill)
        for bill in list_bills(session, account_id=account_id, limit=limit)
    ]
