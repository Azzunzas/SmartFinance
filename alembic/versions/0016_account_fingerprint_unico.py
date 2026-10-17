"""fingerprint de conta vira único, pra reconexão não duplicar a conta

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-24

Reconectar um banco pelo MeuPluggy gera `itemId` e `accountId` novos para as
MESMAS contas físicas. O `upsert_account` casava só por `pluggy_account_id`,
então a reconexão inseria linhas novas e as antigas continuavam com
`is_own=true` e `include_in_analysis=true`. Como `load_overview` filtra por
esses dois campos e não olha se a conexão ainda está ativa, patrimônio líquido
e fatura aberta passariam a contar a mesma conta duas vezes.

E não se resolvia sozinho: a conta velha para de receber `balance_snapshot`,
mas o `/metrics/networth` faz forward-fill do último saldo conhecido — o saldo
congelado somaria na série histórica para sempre. `connection.superseded_by`
existe na tabela e nenhuma linha de código escreve nela; a desativação por 404
só dispara se o item antigo continuar sendo sincronizado, o que deixa de
acontecer assim que o `PLUGGY_ITEM_ID` do Secret é trocado.

A coluna `account.fingerprint` foi criada na 0001 exatamente para dizer "é a
mesma conta física" (`connector_id|subtype|número_mascarado`), mas o índice era
btree comum e por isso não servia de alvo para `ON CONFLICT`. Esta migration
troca por único; o `upsert_account` passa a casar por ele e a linha existente
adota o `pluggy_account_id` novo, preservando id interno, transações,
snapshots e cursor.

Verificado no banco real antes de aplicar: 6 contas, nenhum fingerprint
repetido e nenhum nulo.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_account_fingerprint", table_name="account")
    op.create_index("ux_account_fingerprint", "account", ["fingerprint"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_account_fingerprint", table_name="account")
    op.create_index("ix_account_fingerprint", "account", ["fingerprint"])
