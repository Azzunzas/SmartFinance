import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.analysis.alerts import ConnectionSnapshot
from core.models import Connection

_UPDATABLE_FIELDS = (
    "status",
    "execution_status",
    "last_updated_at",
    "consent_expires_at",
    "raw",
)


@dataclass(frozen=True, slots=True)
class ConnectionUpsert:
    pluggy_item_id: uuid.UUID
    connector_id: int
    connector_name: str
    status: str
    execution_status: str | None
    last_updated_at: datetime | None
    consent_expires_at: datetime | None
    raw: dict[str, Any]


def upsert_connection(session: Session, values: ConnectionUpsert) -> int:
    """Connection não tem o problema de fingerprint duplicado do §4.2 de
    transaction — é um item só por conexão real, então ON CONFLICT DO UPDATE
    resolve num passo só (sem o cuidado extra de savepoint)."""
    payload = asdict(values)
    stmt = (
        pg_insert(Connection)
        .values(**payload)
        .on_conflict_do_update(
            index_elements=["pluggy_item_id"],
            set_={field: payload[field] for field in _UPDATABLE_FIELDS},
        )
        .returning(Connection.id)
    )
    connection_id: int = session.execute(stmt).scalar_one()
    return connection_id


def load_active_connections(session: Session) -> list[ConnectionSnapshot]:
    """Só conexões `is_active` — uma conexão substituída por reconexão
    (`superseded_by` preenchido em outra linha) não deveria continuar
    disparando alerta pra sempre."""
    rows = session.execute(
        sa.select(
            Connection.id,
            Connection.connector_name,
            Connection.status,
            Connection.last_updated_at,
            Connection.consent_expires_at,
        ).where(Connection.is_active)
    ).all()
    return [
        ConnectionSnapshot(
            connection_id=row.id,
            connector_name=row.connector_name,
            status=row.status,
            last_updated_at=row.last_updated_at,
            consent_expires_at=row.consent_expires_at,
        )
        for row in rows
    ]


def list_active_pluggy_item_ids(session: Session) -> list[str]:
    """IDs internos necessários ao job; nunca são devolvidos pela API."""
    return [
        str(item_id)
        for item_id in session.scalars(
            sa.select(Connection.pluggy_item_id).where(Connection.is_active).order_by(Connection.id)
        )
    ]


def deactivate_connection_by_item_id(session: Session, item_id: str) -> bool:
    """Desativa uma conexão que a Pluggy confirmou que não existe mais.

    A linha é preservada para manter o vínculo e o histórico financeiro local.
    """
    connection = session.scalar(
        sa.select(Connection).where(Connection.pluggy_item_id == uuid.UUID(item_id))
    )
    if connection is None:
        return False

    connection.is_active = False
    session.flush()
    return True


def load_connection_id_by_item_id(session: Session, item_id: str) -> int | None:
    """Id interno da conexão a partir do id da Pluggy.

    Existe para o caminho de falha do sync manual: o `sync_run` que o
    `sync_item` tinha criado (já com `connection_id`) morre no rollback junto
    com a transação que falhou, então a linha de falha precisa reencontrar a
    conexão por fora. Sem isso a alternativa seria guardar o `item_id` no texto
    do erro — que é justamente o identificador que `core/redaction.py` apaga.
    """
    return session.scalar(
        sa.select(Connection.id).where(Connection.pluggy_item_id == uuid.UUID(item_id))
    )
