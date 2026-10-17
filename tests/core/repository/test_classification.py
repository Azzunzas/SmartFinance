import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Account, Connection, Transaction, TransactionClassification
from core.models.transaction import Direction, TxStatus
from core.repository.classification import (
    ClassificationUpsert,
    count_manual_overrides,
    upsert_auto_classification,
    upsert_manual_classification,
)
from tests.helpers import as_instant


@pytest.fixture
def transaction_id(db_session: Session) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()

    account = Account(
        connection_id=connection.id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint="acc-fp-classification-test",
        type="BANK",
        currency_code="BRL",
        raw={},
    )
    db_session.add(account)
    db_session.flush()

    transaction = Transaction(
        account_id=account.id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint="tx-fp-classification-test",
        description="PADARIA DO ZE",
        description_norm="padaria do ze",
        amount=Decimal("-12.50"),
        amount_abs=Decimal("12.50"),
        direction=Direction.OUT,
        currency_code="BRL",
        date=date(2026, 1, 5),
        occurred_at=as_instant(date(2026, 1, 5)),
        accrual_date=date(2026, 1, 5),
        status=TxStatus.POSTED,
        pluggy_category="Eating out",
        raw={},
    )
    db_session.add(transaction)
    db_session.flush()
    return transaction.id


def _auto(session: Session, transaction_id: int, **kwargs: object) -> None:
    """Roda o classificador automático com os valores que o run_analysis teria
    calculado. Default = "não achei nada"."""
    upsert_auto_classification(
        session,
        ClassificationUpsert(
            transaction_id=transaction_id,
            category_id=kwargs.get("category_id"),  # type: ignore[arg-type]
            is_internal_transfer=bool(kwargs.get("is_internal_transfer", False)),
            is_card_payment=bool(kwargs.get("is_card_payment", False)),
            counterpart_tx_id=kwargs.get("counterpart_tx_id"),  # type: ignore[arg-type]
        ),
    )


def _row(session: Session, transaction_id: int) -> TransactionClassification:
    return session.execute(
        select(TransactionClassification).where(
            TransactionClassification.transaction_id == transaction_id
        )
    ).scalar_one()


def test_inserts_new_classification(db_session: Session, transaction_id: int) -> None:
    _auto(db_session, transaction_id)

    row = _row(db_session, transaction_id)
    assert row.is_internal_transfer_auto is False
    assert row.is_internal_transfer_manual is None  # "não opinei"
    assert row.is_internal_transfer is False  # resolvida


def test_updates_existing_auto_classification(db_session: Session, transaction_id: int) -> None:
    counterpart = Transaction(
        account_id=db_session.get_one(Transaction, transaction_id).account_id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint="tx-fp-classification-test-counterpart",
        description="TRANSFERENCIA RECEBIDA",
        description_norm="transferencia recebida",
        amount=Decimal("12.50"),
        amount_abs=Decimal("12.50"),
        direction=Direction.IN,
        currency_code="BRL",
        date=date(2026, 1, 5),
        occurred_at=as_instant(date(2026, 1, 5)),
        accrual_date=date(2026, 1, 5),
        status=TxStatus.POSTED,
        raw={},
    )
    db_session.add(counterpart)
    db_session.flush()

    _auto(db_session, transaction_id)
    _auto(db_session, transaction_id, is_internal_transfer=True, counterpart_tx_id=counterpart.id)

    row = _row(db_session, transaction_id)
    assert row.is_internal_transfer is True
    assert row.counterpart_tx_id == counterpart.id


def test_manual_override_wins_over_auto(db_session: Session, transaction_id: int) -> None:
    """Regra de domínio 7: a decisão manual manda. Mas agora ela manda **na
    leitura**, sem precisar impedir o automático de rodar."""
    _auto(db_session, transaction_id, is_internal_transfer=True)
    upsert_manual_classification(db_session, transaction_id, {"is_internal_transfer": False})

    # o automático roda de novo e continua discordando
    _auto(db_session, transaction_id, is_internal_transfer=True)

    row = _row(db_session, transaction_id)
    assert row.is_internal_transfer_auto is True  # o robô manteve a opinião dele
    assert row.is_internal_transfer_manual is False  # a sua também
    assert row.is_internal_transfer is False  # e a sua é a que vale
    assert count_manual_overrides(db_session) == 1


def test_note_does_not_freeze_auto_classification(
    db_session: Session, transaction_id: int
) -> None:
    """Regressão do bug encontrado em 2026-08-23.

    Antes da migration 0013, escrever só uma nota marcava a linha inteira como
    MANUAL e o `run_analysis` nunca mais tocava naquela transação — a
    classificação automática ficava congelada no que fosse naquele instante.
    """
    _auto(db_session, transaction_id, is_internal_transfer=False)
    upsert_manual_classification(db_session, transaction_id, {"note": "conferir depois"})

    # o automático descobre depois que ERA transferência interna
    _auto(db_session, transaction_id, is_internal_transfer=True)

    row = _row(db_session, transaction_id)
    assert row.note == "conferir depois"  # sua nota continua lá
    assert row.is_internal_transfer is True  # e o automático não ficou preso
    assert count_manual_overrides(db_session) == 0  # nota não é override


def test_both_legs_reclassified_when_counterpart_arrives_later(
    db_session: Session, transaction_id: int
) -> None:
    """Regressão do cenário concreto que o bug quebrava: as duas pernas de uma
    transferência interna chegam em syncs de dias diferentes. Se a primeira
    perna tivesse sido tocada à mão (uma nota, por exemplo), ela ficava
    congelada como despesa e só a segunda era excluída — inflando o gasto pela
    metade do valor da transferência."""
    leg_a = transaction_id
    leg_b = Transaction(
        account_id=db_session.get_one(Transaction, leg_a).account_id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint="tx-fp-classification-leg-b",
        description="TRANSFERENCIA RECEBIDA",
        description_norm="transferencia recebida",
        amount=Decimal("12.50"),
        amount_abs=Decimal("12.50"),
        direction=Direction.IN,
        currency_code="BRL",
        date=date(2026, 1, 6),
        occurred_at=as_instant(date(2026, 1, 6)),
        accrual_date=date(2026, 1, 6),
        status=TxStatus.POSTED,
        raw={},
    )
    db_session.add(leg_b)
    db_session.flush()

    # dia 1: só a perna A existe, o detector não acha par
    _auto(db_session, leg_a, is_internal_transfer=False)
    upsert_manual_classification(db_session, leg_a, {"note": "transferencia pra reserva"})

    # dia 2: a perna B chega e o detector casa as duas
    _auto(db_session, leg_a, is_internal_transfer=True, counterpart_tx_id=leg_b.id)
    _auto(db_session, leg_b.id, is_internal_transfer=True, counterpart_tx_id=leg_a)

    assert _row(db_session, leg_a).is_internal_transfer is True
    assert _row(db_session, leg_b.id).is_internal_transfer is True
