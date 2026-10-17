"""fase 2 - category e category_mapping

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-17

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Taxonomia decidida em conversa: achatada por enquanto (sem subcategoria),
# mapeando só as pluggy_category que apareceram de verdade nos dados reais
# sincronizados (PicPay, Nubank, Santander) — não a lista genérica da Pluggy.
_CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "Alimentação": ("EXPENSE", ["Eating out", "Food delivery", "Food and drinks", "Groceries"]),
    "Transporte": (
        "EXPENSE",
        [
            "Automotive",
            "Gas stations",
            "Gas",
            "Parking",
            "Public transportation",
            "Transportation",
            "Vehicle maintenance",
        ],
    ),
    "Compras": (
        "EXPENSE",
        ["Shopping", "Clothing", "Electronics", "Houseware", "Bookstore", "Office supplies"],
    ),
    "Saúde e bem-estar": (
        "EXPENSE",
        ["Pharmacy", "Healthcare", "Wellness", "Wellness and fitness", "Gyms and fitness centers"],
    ),
    "Lazer e assinaturas": (
        "EXPENSE",
        ["Leisure", "Music streaming", "Digital services", "Tickets"],
    ),
    "Educação": ("EXPENSE", ["Education", "University"]),
    "Serviços e contas": ("EXPENSE", ["Telecommunications", "Services", "Insurance"]),
    "Custos financeiros": (
        "EXPENSE",
        [
            "Tax on financial operations",
            "Interests charged",
            "Late payment and overdraft costs",
            "Loans and financing",
            "Wire transfer fees and ATM fees",
        ],
    ),
    "Renda": ("INCOME", ["Salary", "Proceeds interests and dividends"]),
    "Investimentos": ("INVESTMENT", ["Investments", "Automatic investment"]),
    "Transferências": (
        "TRANSFER",
        [
            "Transfer - PIX",
            "Transfers",
            "Same person transfer",
            "Same person transfer - CASH",
            "Transfer - TED",
            "Third party transfer - PIX",
        ],
    ),
    "Pagamento de fatura": ("TRANSFER", ["Credit card payment"]),
}


def upgrade() -> None:
    category = op.create_table(
        "category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("category.id")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
    )
    category_mapping = op.create_table(
        "category_mapping",
        sa.Column("pluggy_category", sa.Text(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=False),
    )

    bind = op.get_bind()
    for name, (kind, pluggy_categories) in _CATEGORIES.items():
        category_id = bind.execute(
            category.insert().values(name=name, kind=kind).returning(category.c.id)
        ).scalar_one()
        bind.execute(
            category_mapping.insert(),
            [
                {"pluggy_category": pluggy_category, "category_id": category_id}
                for pluggy_category in pluggy_categories
            ],
        )


def downgrade() -> None:
    op.drop_table("category_mapping")
    op.drop_table("category")
