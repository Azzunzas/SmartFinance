"""separa classificação automática de override manual

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-23

Motivo (bug encontrado na revisão de 2026-08-23): `transaction_classification`
guardava a decisão do `run_analysis` e a sua correção manual na MESMA coluna,
com uma única flag `source` decidindo quem manda na linha inteira. Consequência:
escrever só uma nota marcava a linha como MANUAL e congelava a classificação
automática de todos os campos pra sempre — o `run_analysis` nunca mais tocava
naquela transação. Com as duas pernas de uma transferência chegando em syncs
diferentes (caso normal), uma perna virava despesa e a outra não.

Desenho novo: cada campo disputado vira três colunas.
  <campo>_auto    -> só o run_analysis escreve
  <campo>_manual  -> só você escreve; NULL = "não opinei"
  <campo>         -> GENERATED, COALESCE(manual, auto), ninguém escreve

O nome antigo continua existindo como coluna gerada, então toda query de
leitura do repo continua funcionando sem mudar uma linha.

`note` e `exclude_from_analysis` NÃO entram nessa separação: o
`upsert_auto_classification` nunca escreveu neles, já eram seus por construção.

`source` é dropada — com cerca por campo ela não tem mais função, e coluna
morta que parece viva é pior que coluna ausente.

ATENÇÃO (verificado empiricamente antes de escrever esta migration): renomear
uma coluna NÃO quebra uma materialized view que a usa — o Postgres reescreve a
definição dela sozinho, apontando pro nome novo. Se a `mv_monthly_cashflow`
não fosse dropada e recriada aqui, ela continuaria lendo as colunas `_auto` e
ignoraria todo override manual, em silêncio, sem erro e sem um REFRESH
resolver. Por isso o drop/create abaixo é obrigatório, não higiene.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Idêntica à da migration 0004. Recriada aqui só pra religar as referências de
# coluna nas colunas GERADAS em vez de nas `_auto` (ver ATENÇÃO no topo).
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

_DISPUTED_BOOL = ("is_internal_transfer", "is_card_payment")


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")

    for column in (*_DISPUTED_BOOL, "category_id", "counterpart_tx_id"):
        op.alter_column("transaction_classification", column, new_column_name=f"{column}_auto")

    op.add_column(
        "transaction_classification",
        sa.Column("category_id_manual", sa.Integer(), sa.ForeignKey("category.id")),
    )
    op.add_column(
        "transaction_classification",
        sa.Column("counterpart_tx_id_manual", sa.BigInteger(), sa.ForeignKey("transaction.id")),
    )
    for column in _DISPUTED_BOOL:
        op.add_column(
            "transaction_classification",
            # anulável de propósito: NULL = "não opinei", distinto de "opinei que é false".
            # É essa distinção que o schema antigo não sabia fazer.
            sa.Column(f"{column}_manual", sa.Boolean()),
        )

    op.add_column(
        "transaction_classification",
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.Computed("COALESCE(category_id_manual, category_id_auto)", persisted=True),
        ),
    )
    op.add_column(
        "transaction_classification",
        sa.Column(
            "counterpart_tx_id",
            sa.BigInteger(),
            sa.Computed(
                "COALESCE(counterpart_tx_id_manual, counterpart_tx_id_auto)", persisted=True
            ),
        ),
    )
    for column in _DISPUTED_BOOL:
        op.add_column(
            "transaction_classification",
            sa.Column(
                column,
                sa.Boolean(),
                sa.Computed(f"COALESCE({column}_manual, {column}_auto)", persisted=True),
                nullable=False,
            ),
        )

    op.drop_column("transaction_classification", "source")

    op.execute(_CREATE_MV)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW mv_monthly_cashflow")

    # As geradas somem primeiro, senão o rename colide com o nome delas.
    for column in (*_DISPUTED_BOOL, "category_id", "counterpart_tx_id"):
        op.drop_column("transaction_classification", column)
        op.drop_column("transaction_classification", f"{column}_manual")
        op.alter_column("transaction_classification", f"{column}_auto", new_column_name=column)

    # Volta pro mundo de uma cerca só. Tudo que existe hoje foi escrito pelo
    # run_analysis, então AUTO é o valor certo pro que sobrou.
    op.add_column(
        "transaction_classification",
        sa.Column("source", sa.Text(), nullable=False, server_default="AUTO"),
    )

    op.execute(_CREATE_MV)
