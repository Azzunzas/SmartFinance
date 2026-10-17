from dataclasses import dataclass
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.models import Connection, SyncRun


@dataclass(frozen=True, slots=True)
class SyncRunRecord:
    id: int
    kind: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    tx_inserted: int
    tx_updated: int
    tx_duplicates: int
    error_message: str | None
    connection_id: int | None
    connector_name: str | None


def list_recent_sync_runs(
    session: Session, limit: int = 20, *, kind: str | None = None
) -> list[SyncRunRecord]:
    statement = sa.select(SyncRun, Connection.connector_name).outerjoin(
        Connection, Connection.id == SyncRun.connection_id
    )
    if kind is not None:
        statement = statement.where(SyncRun.kind == kind)
    rows = session.execute(statement.order_by(SyncRun.started_at.desc()).limit(limit)).all()
    return [
        SyncRunRecord(
            id=row.SyncRun.id,
            kind=row.SyncRun.kind,
            started_at=row.SyncRun.started_at,
            finished_at=row.SyncRun.finished_at,
            status=row.SyncRun.status,
            tx_inserted=row.SyncRun.tx_inserted or 0,
            tx_updated=row.SyncRun.tx_updated or 0,
            tx_duplicates=row.SyncRun.tx_duplicates or 0,
            error_message=row.SyncRun.error_message,
            connection_id=row.SyncRun.connection_id,
            connector_name=row.connector_name,
        )
        for row in rows
    ]
