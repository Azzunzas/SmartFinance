import datetime as dt
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.models import Transaction, TransactionClassification

# Os campos que o run_analysis calcula e que você pode sobrescrever. Um patch
# manual nestes vai pra coluna `<campo>_manual`; o resto (`note`,
# `exclude_from_analysis`) grava na própria coluna, porque o automático nunca
# disputou esses dois. Ver migration 0013.
_DISPUTED_FIELDS = frozenset(
    {"category_id", "is_internal_transfer", "is_card_payment", "counterpart_tx_id"}
)


def _to_manual_columns(patch: dict[str, Any]) -> dict[str, Any]:
    return {(f"{k}_manual" if k in _DISPUTED_FIELDS else k): v for k, v in patch.items()}


@dataclass(frozen=True, slots=True)
class ClassificationUpsert:
    transaction_id: int
    category_id: int | None
    is_internal_transfer: bool
    is_card_payment: bool
    counterpart_tx_id: int | None


def upsert_auto_classification(session: Session, values: ClassificationUpsert) -> None:
    """Grava o que o `run_analysis` calculou, **sempre**, nas colunas `_auto`.

    Não existe mais guarda de `source` aqui — e é essa a correção da migration
    0013. Antes, uma linha marcada MANUAL fazia o automático desistir dela pra
    sempre; bastava você ter escrito uma nota. Agora o automático escreve nas
    colunas dele sem pedir licença, e continua sem conseguir tocar nas suas:
    a coluna gerada resolve `COALESCE(manual, auto)` na leitura, então seu
    override vence sem precisar impedir o automático de rodar.

    Consequência prática: reprocessar tudo passou a ser sempre seguro. Se a
    contraparte de uma transferência chegar num sync posterior, as DUAS pernas
    são reclassificadas — antes, uma delas podia estar congelada.
    """
    auto_values = {
        "category_id_auto": values.category_id,
        "is_internal_transfer_auto": values.is_internal_transfer,
        "is_card_payment_auto": values.is_card_payment,
        "counterpart_tx_id_auto": values.counterpart_tx_id,
    }
    session.execute(
        pg_insert(TransactionClassification)
        .values(transaction_id=values.transaction_id, **auto_values)
        .on_conflict_do_update(
            index_elements=["transaction_id"],
            set_={**auto_values, "updated_at": sa.func.now()},
        )
    )


def count_manual_overrides(session: Session) -> int:
    """Quantas transações têm pelo menos uma decisão sua sobrepondo o
    automático. Substitui o antigo contador `skipped_manual` do `run_analysis`:
    agora nada é "pulado", então o número informativo passou a ser quantos
    overrides existem, não quantas linhas o automático desistiu de tocar."""
    return session.execute(
        sa.select(sa.func.count())
        .select_from(TransactionClassification)
        .where(
            sa.or_(
                TransactionClassification.category_id_manual.is_not(None),
                TransactionClassification.is_internal_transfer_manual.is_not(None),
                TransactionClassification.is_card_payment_manual.is_not(None),
                TransactionClassification.counterpart_tx_id_manual.is_not(None),
            )
        )
    ).scalar_one()


@dataclass(frozen=True, slots=True)
class ClassificationRecord:
    transaction_id: int
    category_id: int | None
    is_internal_transfer: bool
    is_card_payment: bool
    exclude_from_analysis: bool
    counterpart_tx_id: int | None
    note: str | None
    updated_at: dt.datetime


def _to_record(row: TransactionClassification) -> ClassificationRecord:
    return ClassificationRecord(
        transaction_id=row.transaction_id,
        category_id=row.category_id,
        is_internal_transfer=row.is_internal_transfer,
        is_card_payment=row.is_card_payment,
        exclude_from_analysis=row.exclude_from_analysis,
        counterpart_tx_id=row.counterpart_tx_id,
        note=row.note,
        updated_at=row.updated_at,
    )


def upsert_manual_classification(
    session: Session,
    transaction_id: int,
    patch: dict[str, Any],
    reset_fields: list[str] | None = None,
) -> ClassificationRecord | None:
    """Grava a sua decisão nas colunas `_manual`, sem guarda nenhuma — uma
    correção manual sempre vale, inclusive sobre uma correção manual anterior.

    `patch` já vem filtrado por `exclude_unset` do schema Pydantic: só os
    campos que você de fato mandou entram. Campo não mandado continua NULL na
    coluna `_manual`, o que significa "não opinei" e deixa o automático
    valendo pra ele — diferente do schema antigo, em que mexer num campo
    congelava todos os outros junto.

    O valor devolvido vem do `RETURNING`, ou seja, já é o valor **resolvido**
    pelas colunas geradas (`COALESCE(manual, auto)`), não o que você mandou.
    """
    exists = session.execute(
        sa.select(Transaction.id).where(Transaction.id == transaction_id)
    ).scalar_one_or_none()
    if exists is None:
        return None

    manual_patch = _to_manual_columns(patch)
    manual_patch.update({f"{field}_manual": None for field in reset_fields or []})
    stmt = (
        pg_insert(TransactionClassification)
        .values(transaction_id=transaction_id, **manual_patch)
        .on_conflict_do_update(
            index_elements=["transaction_id"],
            set_={**manual_patch, "updated_at": sa.func.now()},
        )
        .returning(TransactionClassification)
    )
    row = session.execute(stmt).scalar_one()
    return _to_record(row)


def bulk_upsert_manual_classification(
    session: Session,
    transaction_ids: list[int],
    patch: dict[str, Any],
    reset_fields: list[str] | None = None,
) -> tuple[list[int], list[int]]:
    """Aplica a mesma `patch` a vários ids, um upsert por vez — volume de
    dado de usuário único não justifica um UPDATE em massa mais complexo.
    Devolve (updated_ids, missing_ids) em vez de falhar o lote inteiro por
    causa de um id que não existe."""
    updated: list[int] = []
    missing: list[int] = []
    for transaction_id in transaction_ids:
        record = upsert_manual_classification(session, transaction_id, patch, reset_fields)
        if record is None:
            missing.append(transaction_id)
        else:
            updated.append(transaction_id)
    return updated, missing
