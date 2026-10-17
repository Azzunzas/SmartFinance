from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SyncRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class SyncAcceptedOut(BaseModel):
    accepted: bool = True


class SyncStatusOut(BaseModel):
    running: bool
