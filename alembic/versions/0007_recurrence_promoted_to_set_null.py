"""fase 4 - recurrence_candidate.promoted_to vira ON DELETE SET NULL

Apagar o planned_item promovido não deveria travar (não é dado histórico
irrecuperável como transaction/planned_item_match) — deveria só liberar o
candidato pra ser promovido de novo.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-18

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "recurrence_candidate_promoted_to_fkey"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "recurrence_candidate", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "recurrence_candidate",
        "planned_item",
        ["promoted_to"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "recurrence_candidate", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT, "recurrence_candidate", "planned_item", ["promoted_to"], ["id"]
    )
