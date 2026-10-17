import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(sa.Integer, sa.ForeignKey("category.id"))
    name: Mapped[str] = mapped_column(sa.Text)
    kind: Mapped[str] = mapped_column(sa.Text)


class CategoryMapping(Base):
    __tablename__ = "category_mapping"

    pluggy_category: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    category_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("category.id"))
