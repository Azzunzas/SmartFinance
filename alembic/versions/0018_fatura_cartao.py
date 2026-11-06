"""fatura de cartão como entidade própria + operationType da transação

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-06

Motivo (conferido no banco real e na API em 2026-11-06): o app tratava
`account.balance` das contas CREDIT como "fatura em aberto", mas esse número
é o **limite usado** — inclui parcelas futuras e compras adiadas ("pula
compra"). No PicPay, R$ 2.803,00 de limite usado contra uma fatura fechada de
R$ 2.517,59. E o vencimento vinha de `creditData.balanceDueDate`, que no cartão
Free continuava em 10/10 semanas depois de vencido.

`GET /bills` da Pluggy devolve cada fatura fechada com valor, vencimento,
fechamento, mínimo e encargos. Testado contra os dois cartões reais via
MeuPluggy: valores em reais (não centavos), só faturas já fechadas, e o total
de cada uma bate centavo a centavo com o pagamento feito.

`transaction.operation_type` é gerada a partir do `raw`, não gravada pelo sync:
o campo já chega da Pluggy desde setembro de 2026 e está guardado no `raw` de
todas as transações recentes. Coluna gerada preenche o histórico sem backfill
e continua certa mesmo que uma versão antiga do sync (sem saber da coluna)
grave a linha.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "transaction",
        sa.Column(
            "operation_type",
            sa.Text(),
            sa.Computed("raw ->> 'operationType'", persisted=True),
        ),
    )

    op.create_table(
        "credit_card_bill",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("pluggy_bill_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("close_date", sa.Date()),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("minimum_payment", sa.Numeric(14, 2)),
        sa.Column("finance_charges_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("currency_code", sa.CHAR(3), nullable=False, server_default="BRL"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_credit_card_bill_account_due",
        "credit_card_bill",
        ["account_id", sa.text("due_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_card_bill_account_due", table_name="credit_card_bill")
    op.drop_table("credit_card_bill")
    op.drop_column("transaction", "operation_type")
