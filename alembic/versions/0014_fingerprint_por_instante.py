"""fingerprint passa a usar o instante da transação, não só o dia

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-23

O fingerprint identificava uma transação por (conta, DIA, valor, direção,
descrição normalizada). Duas transações reais e distintas no mesmo dia, com
mesmo valor e mesma descrição genérica — "PIX recebido" de R$7, por exemplo —
produziam o mesmo fingerprint, e o índice único fazia a segunda ser descartada
na ingestão.

Medido contra a API da Pluggy em 2026-08-23: **6 transações** já tinham sido
engolidas assim, em duas contas BANK, todas entrada de dinheiro. Ou seja, a
receita estava subestimada.

Descartados como discriminador antes de escolher o horário:
  - `balance` (saldo após a transação): a Pluggy manda None nas 858 checadas.
  - `providerId`/`providerCode`: também None.
O horário separou 6 de 6 colisões reais, e nenhuma transação vem à meia-noite —
é informação de verdade tanto em BANK quanto em CREDIT.

Esta migration:
  1. adiciona `transaction.occurred_at` (o instante reportado pela Pluggy),
  2. preenche a partir de `raw->>'date'`, que tem o timestamp cheio nas 826
     linhas existentes,
  3. recalcula TODOS os fingerprints com o algoritmo novo.

O cálculo do hash está copiado inline de propósito, e não importado de
`core.ingestion.normalize`: migration tem que continuar reproduzível daqui a um
ano, mesmo que aquela função mude de novo.
"""
import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CENTS = Decimal("0.01")


def _fingerprint(
    account_fingerprint: str,
    occurred_at: datetime,
    amount_abs: Decimal,
    direction: str,
    description_norm: str,
) -> str:
    raw = (
        f"{account_fingerprint}|{occurred_at.astimezone(UTC).isoformat()}|"
        f"{amount_abs.quantize(_CENTS)}|{direction}|{description_norm}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def upgrade() -> None:
    op.add_column(
        "transaction", sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    # `raw->>'date'` é ISO-8601 com Z; o cast do Postgres resolve o fuso.
    op.execute(
        "UPDATE transaction SET occurred_at = (raw->>'date')::timestamptz "
        "WHERE raw ? 'date'"
    )
    # Fallback pras linhas (nenhuma hoje) sem `date` no raw: meia-noite UTC do
    # dia civil. Perde precisão, mas mantém a coluna NOT NULL sem inventar dado
    # de outra linha.
    op.execute("UPDATE transaction SET occurred_at = date::timestamptz WHERE occurred_at IS NULL")
    op.alter_column("transaction", "occurred_at", nullable=False)

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT t.id, a.fingerprint, t.occurred_at, t.amount_abs, t.direction, "
            "t.description_norm FROM transaction t JOIN account a ON a.id = t.account_id"
        )
    ).all()
    for row in rows:
        connection.execute(
            sa.text("UPDATE transaction SET fingerprint = :fp WHERE id = :id"),
            {
                "fp": _fingerprint(row[1], row[2], row[3], row[4], row[5]),
                "id": row[0],
            },
        )


def downgrade() -> None:
    """Volta o fingerprint pro algoritmo por dia. Atenção: se depois da 0014
    entraram duas transações que só o horário separava, elas colidem aqui e o
    índice único faz o downgrade FALHAR — de propósito. Falhar alto é melhor
    que escolher sozinho qual das duas apagar."""
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT t.id, a.fingerprint, t.date, t.amount_abs, t.direction, "
            "t.description_norm FROM transaction t JOIN account a ON a.id = t.account_id"
        )
    ).all()
    for row in rows:
        raw = (
            f"{row[1]}|{row[2].isoformat()}|{row[3].quantize(_CENTS)}|{row[4]}|{row[5]}"
        )
        connection.execute(
            sa.text("UPDATE transaction SET fingerprint = :fp WHERE id = :id"),
            {"fp": hashlib.sha256(raw.encode()).hexdigest(), "id": row[0]},
        )
    op.drop_column("transaction", "occurred_at")
