import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.models import Account, BalanceSnapshot

_UPDATABLE_FIELDS = (
    # Reconexão: a mesma conta física volta com identificadores novos, e a linha
    # existente precisa adotá-los em vez de virar uma segunda linha. Ver a
    # migration 0016 e o comentário em `upsert_account`.
    "pluggy_account_id",
    "connection_id",
    "name",
    "balance",
    "credit_limit",
    "available_credit_limit",
    "brand",
    "balance_due_date",
    "balance_close_date",
    "minimum_payment",
    "raw",
)
"""O que o sync pode reescrever numa conta que já existe.

Fora daqui de propósito: `is_own` e `include_in_analysis` são decisão do
usuário, não dado da Pluggy — se entrassem, cada sync desfaria a escolha de
excluir uma conta da análise. `fingerprint`, `type`, `subtype` e
`number_masked` também ficam fora: os três últimos compõem o fingerprint, então
mudar qualquer um deles é, por definição, outra conta.
"""


@dataclass(frozen=True, slots=True)
class AccountUpsert:
    connection_id: int
    pluggy_account_id: uuid.UUID
    fingerprint: str
    type: str
    subtype: str | None
    name: str | None
    number_masked: str | None
    currency_code: str
    balance: Decimal
    credit_limit: Decimal | None
    available_credit_limit: Decimal | None
    brand: str | None
    balance_due_date: date | None
    balance_close_date: date | None
    minimum_payment: Decimal | None
    raw: dict[str, Any]


def upsert_account(session: Session, values: AccountUpsert) -> int:
    """Identidade da conta é o `fingerprint`, não o `pluggy_account_id`.

    Reconectar um banco pelo MeuPluggy gera `accountId` novo para a MESMA conta
    física. Casando por `pluggy_account_id` (como era até 2026-08-24), a
    reconexão inseria uma linha nova e a antiga continuava sendo somada no
    patrimônio — com o agravante de o `/metrics/networth` fazer forward-fill do
    saldo congelado dela para sempre. Casando por `fingerprint`
    (`connector_id|subtype|número_mascarado`), a linha existente adota os
    identificadores novos e mantém id interno, transações, snapshots e cursor.
    """
    payload = asdict(values)
    stmt = (
        pg_insert(Account)
        .values(**payload)
        .on_conflict_do_update(
            index_elements=["fingerprint"],
            set_={
                **{field: payload[field] for field in _UPDATABLE_FIELDS},
                "updated_at": sa.func.now(),
            },
        )
        .returning(Account.id)
    )
    account_id: int = session.execute(stmt).scalar_one()
    capture_balance_snapshot(session, account_id, values.balance)
    return account_id


def capture_balance_snapshot(session: Session, account_id: int, balance: Decimal) -> None:
    """§3.2 do arquitetura doc: a Pluggy só dá o saldo atual, não histórico —
    o que não for capturado aqui está perdido pra sempre. DO NOTHING é só uma
    trava defensiva pro caso (raro) de dois syncs caírem no mesmo instante."""
    session.execute(
        pg_insert(BalanceSnapshot)
        .values(account_id=account_id, captured_at=sa.func.now(), balance=balance)
        .on_conflict_do_nothing()
    )


@dataclass(frozen=True, slots=True)
class AccountRecord:
    id: int
    type: str
    subtype: str | None
    name: str | None
    number_masked: str | None
    currency_code: str
    balance: Decimal | None
    credit_limit: Decimal | None
    available_credit_limit: Decimal | None
    brand: str | None
    balance_due_date: date | None
    balance_close_date: date | None
    minimum_payment: Decimal | None
    is_own: bool
    include_in_analysis: bool
    updated_at: datetime


def list_accounts(session: Session, *, account_type: str | None = None) -> list[AccountRecord]:
    query = sa.select(Account).order_by(Account.type, Account.name)
    if account_type is not None:
        query = query.where(Account.type == account_type)

    rows = session.execute(query).scalars().all()
    return [
        AccountRecord(
            id=row.id,
            type=row.type,
            subtype=row.subtype,
            name=row.name,
            number_masked=row.number_masked,
            currency_code=row.currency_code,
            balance=row.balance,
            credit_limit=row.credit_limit,
            available_credit_limit=row.available_credit_limit,
            brand=row.brand,
            balance_due_date=row.balance_due_date,
            balance_close_date=row.balance_close_date,
            minimum_payment=row.minimum_payment,
            is_own=row.is_own,
            include_in_analysis=row.include_in_analysis,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
