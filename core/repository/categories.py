from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.analysis.classify import CategoryLookup
from core.models import Category, CategoryMapping


@dataclass(frozen=True, slots=True)
class CategoryRecord:
    id: int
    parent_id: int | None
    name: str
    kind: str


def list_categories(session: Session) -> list[CategoryRecord]:
    rows = session.execute(sa.select(Category).order_by(Category.name, Category.id)).scalars()
    return [
        CategoryRecord(id=row.id, parent_id=row.parent_id, name=row.name, kind=row.kind)
        for row in rows
    ]


def load_category_mapping(session: Session) -> dict[str, CategoryLookup]:
    rows = session.execute(
        sa.select(
            CategoryMapping.pluggy_category, Category.id, Category.name, Category.kind
        ).join(Category, Category.id == CategoryMapping.category_id)
    ).all()
    return {
        row.pluggy_category: CategoryLookup(
            category_id=row.id, category_name=row.name, kind=row.kind
        )
        for row in rows
    }
