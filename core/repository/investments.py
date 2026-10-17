import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.models import Investment, InvestmentSnapshot

_UPDATABLE_FIELDS = ("name", "type", "subtype", "issuer", "status", "is_active", "raw")


@dataclass(frozen=True, slots=True)
class InvestmentUpsert:
    connection_id: int
    pluggy_investment_id: uuid.UUID
    name: str
    type: str | None
    subtype: str | None
    issuer: str | None
    status: str | None
    is_active: bool
    raw: dict[str, Any]


def upsert_investment(session: Session, values: InvestmentUpsert) -> int:
    payload = asdict(values)
    stmt = (
        pg_insert(Investment)
        .values(**payload)
        .on_conflict_do_update(
            index_elements=["pluggy_investment_id"],
            set_={field: payload[field] for field in _UPDATABLE_FIELDS},
        )
        .returning(Investment.id)
    )
    investment_id: int = session.execute(stmt).scalar_one()
    return investment_id


def capture_investment_snapshot(session: Session, investment_id: int, balance: Decimal) -> None:
    """Doc §3.2: a Pluggy só dá o saldo atual, não histórico — o que não for
    capturado aqui está perdido pra sempre. Mesmo raciocínio de
    `capture_balance_snapshot` pra contas."""
    session.execute(
        pg_insert(InvestmentSnapshot)
        .values(investment_id=investment_id, captured_at=sa.func.now(), balance=balance)
        .on_conflict_do_nothing()
    )


@dataclass(frozen=True, slots=True)
class InvestmentRecord:
    id: int
    name: str
    type: str | None
    subtype: str | None
    issuer: str | None
    status: str | None
    is_active: bool
    balance: Decimal | None


def list_investments(session: Session, *, active_only: bool = True) -> list[InvestmentRecord]:
    """`balance` é o snapshot mais recente de cada investimento, não uma
    coluna em `investment` — a tabela não guarda saldo (só metadado). Usa
    `row_number()` particionado por `investment_id` em vez de um MAX(...)
    correlacionado por linha: com "captura desde o dia 1" (doc §3.2), o
    histórico de snapshot só cresce, e um `MAX` por linha faria um scan do
    histórico inteiro por investimento a cada consulta."""
    latest = (
        sa.select(
            InvestmentSnapshot.investment_id,
            InvestmentSnapshot.balance,
            sa.func.row_number()
            .over(
                partition_by=InvestmentSnapshot.investment_id,
                order_by=InvestmentSnapshot.captured_at.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )
    latest_balance = sa.select(latest.c.investment_id, latest.c.balance).where(
        latest.c.rn == 1
    ).subquery()

    query = sa.select(Investment, latest_balance.c.balance).outerjoin(
        latest_balance, latest_balance.c.investment_id == Investment.id
    )
    if active_only:
        query = query.where(Investment.is_active)
    query = query.order_by(Investment.name)

    rows = session.execute(query).all()
    return [
        InvestmentRecord(
            id=row.Investment.id,
            name=row.Investment.name,
            type=row.Investment.type,
            subtype=row.Investment.subtype,
            issuer=row.Investment.issuer,
            status=row.Investment.status,
            is_active=row.Investment.is_active,
            balance=row.balance,
        )
        for row in rows
    ]
