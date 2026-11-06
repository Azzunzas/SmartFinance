"""crédito no cartão abate gasto, não é receita + crédito parcelado da conta

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-06

Motivo (banco real, outubro de 2026): estornos e "pula compra" chegam como
crédito (`direction = IN`) na conta do cartão. A `mv_monthly_cashflow` somava
todo IN em `total_in`, então R$ 395,94 de créditos no cartão viraram
**receita** em outubro — R$ 123,06 de estornos e R$ 272,88 de "pula compra",
que é o banco tirando a compra desta fatura para cobrar depois. Nenhum dos dois
é renda.

Regra nova (regras do projeto §2, regra 11): crédito no cartão que sobrevive às
exclusões de sempre (não é pagamento de fatura nem transferência interna) abate
`total_out` do mês em que foi lançado. `net` não muda — só deixa de inflar
receita e gasto ao mesmo tempo.

`transaction.is_card_credit` é resolvido na ingestão, como `direction`, pelo
mesmo motivo da regra de domínio 9: a view não pode decidir por
`account.type`. O backfill abaixo usa o tipo da conta uma única vez, para o
histórico.

`account.installment_credit_used`: quanto do limite está em
`CREDITO_PARCELADO` (linha de `creditData.disaggregatedCreditLimits`). No
PicPay, é onde o "pula compra" fica até voltar numa fatura futura: R$ 284,79,
contra R$ 272,88 adiados. Backfill a partir do `raw`, que já guardava a lista.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE_MV_CARD_CREDIT = """
CREATE MATERIALIZED VIEW mv_monthly_cashflow AS
SELECT
    to_char(t.accrual_date, 'YYYY-MM')                                       AS period,
    COALESCE(SUM(t.amount_abs) FILTER (WHERE t.direction = 'IN'
                                         AND NOT t.is_card_credit), 0)       AS total_in,
    COALESCE(SUM(t.amount_abs) FILTER (WHERE t.direction = 'OUT'), 0)
      - COALESCE(SUM(t.amount_abs) FILTER (WHERE t.is_card_credit), 0)       AS total_out,
    SUM(CASE WHEN t.direction = 'IN'  THEN t.amount_abs
             ELSE -t.amount_abs END)                                         AS net
FROM transaction t
JOIN account a ON a.id = t.account_id
LEFT JOIN transaction_classification c ON c.transaction_id = t.id
WHERE t.status = 'POSTED'
  AND a.include_in_analysis
  AND COALESCE(c.is_internal_transfer, FALSE) = FALSE
  AND COALESCE(c.is_card_payment,      FALSE) = FALSE
  AND COALESCE(c.exclude_from_analysis,FALSE) = FALSE
GROUP BY 1
"""

# Idêntica à da 0017.
_CREATE_MV_0017 = """
CREATE MATERIALIZED VIEW mv_monthly_cashflow AS
SELECT
    to_char(t.accrual_date, 'YYYY-MM')                                  AS period,
    COALESCE(SUM(t.amount_abs) FILTER (WHERE t.direction = 'IN'), 0)    AS total_in,
    COALESCE(SUM(t.amount_abs) FILTER (WHERE t.direction = 'OUT'), 0)   AS total_out,
    SUM(CASE WHEN t.direction = 'IN'  THEN t.amount_abs
             ELSE -t.amount_abs END)                                    AS net
FROM transaction t
JOIN account a ON a.id = t.account_id
LEFT JOIN transaction_classification c ON c.transaction_id = t.id
WHERE t.status = 'POSTED'
  AND a.include_in_analysis
  AND COALESCE(c.is_internal_transfer, FALSE) = FALSE
  AND COALESCE(c.is_card_payment,      FALSE) = FALSE
  AND COALESCE(c.exclude_from_analysis,FALSE) = FALSE
GROUP BY 1
"""


def upgrade() -> None:
    op.add_column(
        "transaction",
        sa.Column("is_card_credit", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        """
        UPDATE transaction t
        SET is_card_credit = TRUE
        FROM account a
        WHERE a.id = t.account_id AND a.type = 'CREDIT' AND t.direction = 'IN'
        """
    )

    op.add_column("account", sa.Column("installment_credit_used", sa.Numeric(14, 2)))
    op.execute(
        """
        UPDATE account
        SET installment_credit_used = lines.used
        FROM (
            SELECT a.id, SUM((line ->> 'usedAmount')::numeric) AS used
            FROM account a,
                 jsonb_array_elements(
                     CASE WHEN jsonb_typeof(a.raw -> 'creditData' -> 'disaggregatedCreditLimits')
                               = 'array'
                          THEN a.raw -> 'creditData' -> 'disaggregatedCreditLimits'
                          ELSE '[]'::jsonb END
                 ) AS line
            WHERE line ->> 'lineName' = 'CREDITO_PARCELADO'
            GROUP BY a.id
        ) AS lines
        WHERE account.id = lines.id
        """
    )

    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")
    op.execute(_CREATE_MV_CARD_CREDIT)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")
    op.execute(_CREATE_MV_0017)
    op.drop_column("account", "installment_credit_used")
    op.drop_column("transaction", "is_card_credit")
