"""fase 2 - mv_monthly_cashflow

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-17

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# SQL exato do arquitetura doc §5 — sem decisão de design nova aqui, só
# materializar o que já estava especificado.
_CREATE_MV = """
CREATE MATERIALIZED VIEW mv_monthly_cashflow AS
SELECT
    to_char(t.accrual_date, 'YYYY-MM')                             AS period,
    SUM(t.amount_abs) FILTER (WHERE t.direction = 'IN')            AS total_in,
    SUM(t.amount_abs) FILTER (WHERE t.direction = 'OUT')           AS total_out,
    SUM(CASE WHEN t.direction = 'IN'  THEN t.amount_abs
             ELSE -t.amount_abs END)                               AS net
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
    op.execute(_CREATE_MV)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")
