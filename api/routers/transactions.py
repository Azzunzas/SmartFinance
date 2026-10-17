import base64
import binascii
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.transactions import (
    BulkClassifyRequest,
    BulkClassifyResponse,
    TransactionClassificationOut,
    TransactionClassificationUpdate,
    TransactionOut,
    TransactionPageOut,
)
from core.models.transaction import Direction
from core.repository.classification import (
    bulk_upsert_manual_classification,
    upsert_manual_classification,
)
from core.repository.transactions import list_transactions

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _encode_cursor(row_date: date, row_id: int) -> str:
    raw = f"{row_date.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        date_part, id_part = raw.split("|")
        return date.fromisoformat(date_part), int(id_part)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=422, detail="cursor inválido") from exc


@router.get("", response_model=TransactionPageOut)
def list_all(
    period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    direction: Direction | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    payment_method: str | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> TransactionPageOut:
    """Doc §6.2: `GET /api/transactions?period=&category=&direction=&cursor=`.
    Mostra transferência interna e pagamento de fatura sem esconder de
    propósito — essa tela é onde uma classificação errada é corrigida, as
    exclusões (§4.3 do doc) valem só pras métricas agregadas."""
    after = _decode_cursor(cursor) if cursor else None

    page = list_transactions(
        session,
        period=period,
        direction=direction,
        account_id=account_id,
        category_id=category_id,
        payment_method=payment_method,
        search=search,
        after=after,
        limit=limit,
    )

    next_cursor = None
    if page.has_more and page.items:
        last = page.items[-1]
        next_cursor = _encode_cursor(last.date, last.id)

    return TransactionPageOut(
        items=[TransactionOut.model_validate(item) for item in page.items],
        next_cursor=next_cursor,
    )


@router.patch("/{transaction_id}/classification", response_model=TransactionClassificationOut)
def patch_classification(
    transaction_id: int,
    body: TransactionClassificationUpdate,
    session: Session = Depends(get_session),
) -> TransactionClassificationOut:
    """Doc §6.2: `PATCH /api/transactions/{id}/classification`.

    Grava nas colunas `_manual` (migration 0013). Só os campos que vierem no
    corpo viram override; os que não vierem continuam seguindo o automático,
    em vez de congelar a transação inteira como acontecia antes."""
    patch = body.model_dump(exclude_unset=True)
    reset_fields = patch.pop("reset_fields", [])
    record = upsert_manual_classification(session, transaction_id, patch, reset_fields)
    if record is None:
        raise HTTPException(status_code=404, detail="transação não encontrada")
    return TransactionClassificationOut.model_validate(record)


@router.post("/bulk-classify", response_model=BulkClassifyResponse)
def bulk_classify(
    body: BulkClassifyRequest, session: Session = Depends(get_session)
) -> BulkClassifyResponse:
    """Doc §6.2: `POST /api/transactions/bulk-classify` — aplica a mesma
    classificação a vários ids; ids que não existem entram em `missing_ids`
    em vez de derrubar o lote inteiro."""
    patch = body.model_dump(exclude_unset=True, exclude={"transaction_ids"})
    reset_fields = patch.pop("reset_fields", [])
    updated, missing = bulk_upsert_manual_classification(
        session, body.transaction_ids, patch, reset_fields
    )
    return BulkClassifyResponse(updated_ids=updated, missing_ids=missing)
