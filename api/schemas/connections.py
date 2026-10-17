from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConnectionHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connection_id: int
    connector_name: str
    status: str
    last_updated_at: datetime | None
    consent_expires_at: datetime | None
    consent_expiring: bool
    connection_stale: bool
