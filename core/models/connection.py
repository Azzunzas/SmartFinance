import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Connection(Base):
    __tablename__ = "connection"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    pluggy_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    connector_id: Mapped[int] = mapped_column(sa.Integer)
    connector_name: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[str] = mapped_column(sa.Text)
    execution_status: Mapped[str | None] = mapped_column(sa.Text)
    last_updated_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True))
    consent_expires_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True))
    superseded_by: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("connection.id")
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.true())
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
