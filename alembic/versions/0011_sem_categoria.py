"""category "Sem categoria"

Bucket real pra transação sem `category_id` (Pluggy não mandou categoria, ou
mandou uma que `category_mapping` não cobre — `resolve_category` continua
retornando `None` de propósito, isso não muda). Existe só pra
`GET /api/metrics/categories` ter um nome pra mostrar em vez de esconder a
lacuna; `transaction_classification.category_id` continua `NULL` até o
usuário reclassificar manualmente pela tela (decisão de 2026-08-21).

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-21

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "Sem categoria"


def upgrade() -> None:
    category = sa.table(
        "category",
        sa.column("id", sa.Integer),
        sa.column("name", sa.Text),
        sa.column("kind", sa.Text),
    )
    op.execute(category.insert().values(name=_NAME, kind="EXPENSE"))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM category WHERE name = :name").bindparams(name=_NAME))
