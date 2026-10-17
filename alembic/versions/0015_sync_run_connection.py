"""sync_run.connection_id

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-23

`sync_run` não registrava a qual conexão a execução pertencia. Na prática isso
significava que a ÚNICA pista de qual banco falhou era o UUID que vazava dentro
de `error_message` (a exceção da httpx carrega a URL inteira) — exatamente o
identificador que docs/regras-do-projeto.md §3 manda manter fora de log.

Com a FK, o diagnóstico fica melhor do que era (dá pra juntar com `connection` e
mostrar o nome do conector na tela) e o texto livre pode ser redigido sem perda.

Anulável de propósito: as execuções já gravadas não têm como ser atribuídas
retroativamente, e o sync manual agregado (`kind='MANUAL'`) cobre várias
conexões de uma vez — pra ele, NULL é a resposta certa, não uma lacuna.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_run",
        sa.Column("connection_id", sa.BigInteger(), sa.ForeignKey("connection.id"), nullable=True),
    )
    op.create_index("ix_sync_run_connection", "sync_run", ["connection_id"])

    # As execuções já gravadas carregam o item_id cru dentro de error_message —
    # é justamente o que o core/redaction.py passou a evitar. Limpar o passado
    # também, senão a correção só valeria dali pra frente.
    op.execute(
        r"UPDATE sync_run SET error_message = regexp_replace(error_message, "
        r"'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', "
        r"'<id-omitido>', 'g') WHERE error_message IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_sync_run_connection", table_name="sync_run")
    op.drop_column("sync_run", "connection_id")
