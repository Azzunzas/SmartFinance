import datetime as dt
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.ingestion.normalize import normalize_description
from core.models.account import Account
from core.models.category import Category
from core.models.classification import TransactionClassification
from core.models.transaction import Direction, Transaction, TxStatus

UpsertOutcome = Literal["inserted", "updated", "duplicate"]

# Doc §4.2: no conflito por pluggy_transaction_id, só reescreve o que a Pluggy
# pode legitimamente mudar entre syncs (ex: PENDING -> POSTED). Campos derivados
# na ingestão (fingerprint, description_norm, direction...) não entram aqui —
# eles são calculados uma vez e ficam estáveis pra vida da linha.
_UPDATABLE_FIELDS = ("status", "amount", "amount_abs", "pluggy_category", "payment_method", "raw")


@dataclass(frozen=True, slots=True)
class TransactionUpsert:
    account_id: int
    pluggy_transaction_id: uuid.UUID
    fingerprint: str
    description: str
    description_norm: str
    merchant_name: str | None
    amount: Decimal
    amount_abs: Decimal
    direction: Direction
    currency_code: str
    date: dt.date
    occurred_at: dt.datetime
    accrual_date: dt.date
    status: TxStatus
    installment_number: int | None
    installment_total: int | None
    pluggy_category: str | None
    payment_method: str | None
    balance_after: Decimal | None
    raw: dict[str, Any]


def upsert_transaction(session: Session, values: TransactionUpsert) -> UpsertOutcome:
    """Upsert idempotente descrito no §4.2 do arquitetura doc, em dois passos:

    1. INSERT ... ON CONFLICT (pluggy_transaction_id) DO NOTHING — se a Pluggy já
       mandou essa transação antes, não tenta inserir de novo.
    2. Se nada foi inserido (já existia), faz um UPDATE explícito nos campos que
       podem mudar entre syncs.

    Se o INSERT tentar de fato acontecer (pluggy_transaction_id é novo) mas colidir
    com o índice único de `fingerprint`, é a MESMA transação chegando de novo com
    id diferente — item reconectado (a Pluggy troca os IDs na reconexão), ou o
    registro recriado quando a transação muda de estado. Isso é "duplicate": não
    inserimos linha nova, e o chamador incrementa `sync_run.tx_duplicates`.

    Mas "duplicate" NÃO significa mais descartar. Verificado contra a API em
    2026-08-23: a Pluggy nunca atualiza um registro no lugar (576 transações
    checadas, todas com `updatedAt == createdAt`), então uma PENDING que vira
    POSTED chega como registro novo. Se a descrição e o valor não mudaram, o
    fingerprint é o mesmo — e descartar era o que fazia uma PENDING ficar PENDING
    pra sempre no nosso banco, mesmo depois de liquidada. Agora a linha existente
    recebe os campos mutáveis da que chegou, pelo fingerprint.
    """
    payload = asdict(values)
    insert_stmt = (
        pg_insert(Transaction)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=["pluggy_transaction_id"])
        .returning(Transaction.id)
    )
    try:
        with session.begin_nested():
            inserted_id = session.execute(insert_stmt).scalar_one_or_none()
    except IntegrityError as exc:
        if "ux_transaction_fingerprint" in str(exc.orig):
            _refresh_by_fingerprint(session, values)
            return "duplicate"
        raise

    if inserted_id is not None:
        return "inserted"

    update_fields: dict[str, Any] = {field: payload[field] for field in _UPDATABLE_FIELDS}
    update_fields["updated_at"] = sa.func.now()
    session.execute(
        sa.update(Transaction)
        .where(Transaction.pluggy_transaction_id == values.pluggy_transaction_id)
        .values(**update_fields)
    )
    return "updated"


def _refresh_by_fingerprint(session: Session, values: TransactionUpsert) -> None:
    """Atualiza a linha já existente com o mesmo fingerprint. Só os campos que a
    Pluggy pode legitimamente mudar entre registros da mesma transação — o
    `pluggy_transaction_id` da linha NÃO é trocado de propósito: o primeiro id
    que vimos continua sendo a chave estável dela, e trocar faria a próxima
    releitura colidir de novo sem convergir."""
    payload = asdict(values)
    update_fields: dict[str, Any] = {field: payload[field] for field in _UPDATABLE_FIELDS}
    update_fields["updated_at"] = sa.func.now()
    session.execute(
        sa.update(Transaction)
        .where(Transaction.fingerprint == values.fingerprint)
        .values(**update_fields)
    )


@dataclass(frozen=True, slots=True)
class TransactionRecord:
    id: int
    account_id: int
    account_name: str | None
    date: dt.date
    accrual_date: dt.date
    description: str
    merchant_name: str | None
    amount: Decimal
    amount_abs: Decimal
    direction: Direction
    status: TxStatus
    installment_number: int | None
    installment_total: int | None
    payment_method: str | None
    category_id: int | None
    category_name: str | None
    category_id_auto: int | None
    category_id_manual: int | None
    is_internal_transfer: bool
    is_internal_transfer_auto: bool
    is_internal_transfer_manual: bool | None
    is_card_payment: bool
    is_card_payment_auto: bool
    is_card_payment_manual: bool | None
    exclude_from_analysis: bool
    note: str | None


@dataclass(frozen=True, slots=True)
class TransactionPage:
    items: list[TransactionRecord]
    has_more: bool


def list_transactions(
    session: Session,
    *,
    period: str | None = None,
    direction: Direction | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    payment_method: str | None = None,
    search: str | None = None,
    after: tuple[dt.date, int] | None = None,
    limit: int = 50,
) -> TransactionPage:
    """Listagem paginada por cursor pra tela operacional de Transações — ao
    contrário de `load_matchable_transactions`/`load_upcoming_transactions`,
    NÃO exclui transferência interna nem pagamento de fatura: é justamente
    aqui que uma classificação errada é corrigida, então a linha crua precisa
    aparecer. `has_more` vem de pedir `limit + 1` e descartar a linha extra —
    dispensa um COUNT(*) só pra saber se existe próxima página."""
    query = (
        sa.select(
            Transaction,
            Account.name.label("account_name"),
            Category.name.label("category_name"),
            TransactionClassification.category_id,
            TransactionClassification.category_id_auto,
            TransactionClassification.category_id_manual,
            TransactionClassification.is_internal_transfer,
            TransactionClassification.is_internal_transfer_auto,
            TransactionClassification.is_internal_transfer_manual,
            TransactionClassification.is_card_payment,
            TransactionClassification.is_card_payment_auto,
            TransactionClassification.is_card_payment_manual,
            TransactionClassification.exclude_from_analysis,
            TransactionClassification.note,
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(
            TransactionClassification,
            TransactionClassification.transaction_id == Transaction.id,
        )
        .outerjoin(Category, Category.id == TransactionClassification.category_id)
    )

    if period is not None:
        query = query.where(sa.func.to_char(Transaction.accrual_date, "YYYY-MM") == period)
    if direction is not None:
        query = query.where(Transaction.direction == direction)
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    if category_id is not None:
        unclassified_category = sa.exists(
            sa.select(Category.id).where(
                Category.id == category_id,
                Category.name == "Sem categoria",
            )
        )
        query = query.where(
            sa.or_(
                TransactionClassification.category_id == category_id,
                sa.and_(
                    TransactionClassification.category_id.is_(None),
                    unclassified_category,
                ),
            )
        )
    if payment_method is not None:
        query = query.where(Transaction.payment_method == payment_method)
    if search:
        query = query.where(Transaction.description_norm.like(f"%{normalize_description(search)}%"))
    if after is not None:
        after_date, after_id = after
        query = query.where(sa.tuple_(Transaction.date, Transaction.id) < (after_date, after_id))

    query = query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit + 1)

    rows = session.execute(query).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [
        TransactionRecord(
            id=row.Transaction.id,
            account_id=row.Transaction.account_id,
            account_name=row.account_name,
            date=row.Transaction.date,
            accrual_date=row.Transaction.accrual_date,
            description=row.Transaction.description,
            merchant_name=row.Transaction.merchant_name,
            amount=row.Transaction.amount,
            amount_abs=row.Transaction.amount_abs,
            direction=row.Transaction.direction,
            status=row.Transaction.status,
            installment_number=row.Transaction.installment_number,
            installment_total=row.Transaction.installment_total,
            payment_method=row.Transaction.payment_method,
            category_id=row.category_id,
            category_name=row.category_name,
            category_id_auto=row.category_id_auto,
            category_id_manual=row.category_id_manual,
            is_internal_transfer=bool(row.is_internal_transfer),
            is_internal_transfer_auto=bool(row.is_internal_transfer_auto),
            is_internal_transfer_manual=row.is_internal_transfer_manual,
            is_card_payment=bool(row.is_card_payment),
            is_card_payment_auto=bool(row.is_card_payment_auto),
            is_card_payment_manual=row.is_card_payment_manual,
            exclude_from_analysis=bool(row.exclude_from_analysis),
            note=row.note,
        )
        for row in rows
    ]
    return TransactionPage(items=items, has_more=has_more)
