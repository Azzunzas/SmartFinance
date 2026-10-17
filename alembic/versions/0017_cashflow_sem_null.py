"""mv_monthly_cashflow: COALESCE nos totais, mês sem entrada é R$ 0 e não NULL

Correção de bug latente, achada em 2026-08-24 por um teste de
`load_health_inputs` — não por observação em produção, porque no banco real
todo mês tem entrada e saída, então nunca estourou.

`SUM(x) FILTER (WHERE ...)` devolve **NULL**, não zero, quando nenhuma linha
casa o filtro. Num mês só de saídas, `total_in` vinha NULL, e:

- `GET /api/metrics/cashflow` responderia **500** — `MonthlyCashflowOut.total_in`
  é `Decimal`, não `Decimal | None`, e o Pydantic recusa;
- o burn rate/taxa de poupança (doc §5) somariam `Decimal + None` e quebrariam
  com `TypeError`.

Mesma família do bug 1.1b (conta sem saldo derrubando a visão geral): coluna
anulável somada sem tratamento, invisível pro mypy porque `Row` do SQLAlchemy
é `Any`.

Corrigido na **origem**, não em cada leitor, pelo mesmo raciocínio da regra de
domínio 9 (normalizar uma vez na entrada em vez de espalhar `CASE WHEN` por
query): já são dois leitores (`load_monthly_cashflow`, `load_health_inputs`), e
um terceiro repetiria o bug.

Aqui zero é a resposta **certa**, não um chute: um mês que existe na view e não
teve nenhuma entrada de dinheiro recebeu R$ 0 de entrada, afirmação diferente
de um mês ausente da view (que é "não sincronizava ainda" — por isso
`load_health_inputs` não faz zero-fill de mês faltante).

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Idêntica à da 0013, com COALESCE em total_in/total_out. `net` não precisa:
# o SUM dele não tem FILTER, então só é NULL se o grupo não existir — e grupo
# que não existe não vira linha.
_CREATE_MV_COALESCED = """
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

_CREATE_MV_ORIGINAL = """
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
    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")
    op.execute(_CREATE_MV_COALESCED)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")
    op.execute(_CREATE_MV_ORIGINAL)
