from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class SyncRun(Base):
    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(sa.Text)
    started_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(sa.Text)
    tx_inserted: Mapped[int | None] = mapped_column(sa.Integer, server_default="0")
    tx_updated: Mapped[int | None] = mapped_column(sa.Integer, server_default="0")
    tx_duplicates: Mapped[int | None] = mapped_column(sa.Integer, server_default="0")
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    # Qual conexão esta execução sincronizou — ver migration 0015. NULL só na
    # linha AGREGADA do sync manual, que cobre todas as conexões de uma vez e
    # por isso não tem um banco pra apontar; as linhas por conexão do mesmo
    # sync manual (kind='MANUAL' também) trazem o vínculo preenchido.
    connection_id: Mapped[int | None] = mapped_column(
        sa.BigInteger, sa.ForeignKey("connection.id")
    )


class SyncCursor(Base):
    __tablename__ = "sync_cursor"

    account_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("account.id"), primary_key=True
    )
    cursor: Mapped[str | None] = mapped_column(sa.Text)
    updated_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), server_default=sa.func.now()
    )
