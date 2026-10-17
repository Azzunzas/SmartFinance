import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.models import Category, CategoryMapping

_VALID_KINDS = {"EXPENSE", "INCOME", "TRANSFER", "INVESTMENT"}


def test_seed_categories_have_valid_kind(db_session: Session) -> None:
    categories = db_session.execute(sa.select(Category)).scalars().all()
    # 12 da migration 0002 (fase 2) + "Sem categoria" da migration 0011
    # (bucket real pra transação sem category_id, ver load_category_spend).
    assert len(categories) == 13
    assert {c.kind for c in categories} <= _VALID_KINDS


def test_every_category_mapping_points_to_existing_category(db_session: Session) -> None:
    orphans = (
        db_session.execute(
            sa.select(CategoryMapping)
            .outerjoin(Category, CategoryMapping.category_id == Category.id)
            .where(Category.id.is_(None))
        )
        .scalars()
        .all()
    )
    assert orphans == []


def test_credit_card_payment_maps_to_transfer_kind(db_session: Session) -> None:
    row = db_session.execute(
        sa.select(Category)
        .join(CategoryMapping, CategoryMapping.category_id == Category.id)
        .where(CategoryMapping.pluggy_category == "Credit card payment")
    ).scalar_one()
    assert row.kind == "TRANSFER"
