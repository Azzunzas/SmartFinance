import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Account, Connection, Transaction
from core.models.transaction import Direction, TxStatus
from core.repository.transactions import TransactionUpsert, upsert_transaction


@pytest.fixture
def account_id(db_session: Session) -> int:
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
        fingerprint="acc-fp-test",
        type="BANK",
        currency_code="BRL",
        raw={},
    )
    db_session.add(account)
    db_session.flush()
    return account.id


def _tx(
    *,
    account_id: int,
    pluggy_transaction_id: uuid.UUID,
    fingerprint: str,
    amount: Decimal = Decimal("-12.50"),
    status: TxStatus = TxStatus.POSTED,
    occurred_at: datetime | None = None,
) -> TransactionUpsert:
    return TransactionUpsert(
        account_id=account_id,
        pluggy_transaction_id=pluggy_transaction_id,
        fingerprint=fingerprint,
        description="PADARIA DO ZE",
        description_norm="padaria do ze",
        merchant_name=None,
        amount=amount,
        amount_abs=abs(amount),
        direction=Direction.OUT,
        currency_code="BRL",
        date=date(2026, 1, 5),
        occurred_at=occurred_at or datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        accrual_date=date(2026, 1, 5),
        status=status,
        installment_number=None,
        installment_total=None,
        pluggy_category="Eating out",
        payment_method=None,
        balance_after=None,
        raw={},
    )


def test_insert_new_transaction(db_session: Session, account_id: int) -> None:
    outcome = upsert_transaction(
        db_session,
        _tx(account_id=account_id, pluggy_transaction_id=uuid.uuid4(), fingerprint="fp-1"),
    )
    assert outcome == "inserted"


def test_upsert_same_pluggy_id_updates_status(db_session: Session, account_id: int) -> None:
    pluggy_id = uuid.uuid4()
    first = upsert_transaction(
        db_session,
        _tx(
            account_id=account_id,
            pluggy_transaction_id=pluggy_id,
            fingerprint="fp-2",
            status=TxStatus.PENDING,
        ),
    )
    second = upsert_transaction(
        db_session,
        _tx(
            account_id=account_id,
            pluggy_transaction_id=pluggy_id,
            fingerprint="fp-2",
            status=TxStatus.POSTED,
        ),
    )

    assert first == "inserted"
    assert second == "updated"

    row = db_session.execute(
        select(Transaction).where(Transaction.pluggy_transaction_id == pluggy_id)
    ).scalar_one()
    assert row.status is TxStatus.POSTED


def test_reconnection_with_new_pluggy_id_same_fingerprint_is_duplicate(
    db_session: Session, account_id: int
) -> None:
    shared_fingerprint = "fp-shared"
    first = upsert_transaction(
        db_session,
        _tx(
            account_id=account_id,
            pluggy_transaction_id=uuid.uuid4(),
            fingerprint=shared_fingerprint,
        ),
    )
    second = upsert_transaction(
        db_session,
        _tx(
            account_id=account_id,
            pluggy_transaction_id=uuid.uuid4(),
            fingerprint=shared_fingerprint,
        ),
    )

    assert first == "inserted"
    assert second == "duplicate"

    count = db_session.execute(
        select(sa.func.count())
        .select_from(Transaction)
        .where(Transaction.fingerprint == shared_fingerprint)
    ).scalar_one()
    assert count == 1


def test_running_upsert_twice_with_identical_data_yields_no_duplicates(
    db_session: Session, account_id: int
) -> None:
    pluggy_id = uuid.uuid4()
    tx = _tx(account_id=account_id, pluggy_transaction_id=pluggy_id, fingerprint="fp-idempotent")

    upsert_transaction(db_session, tx)
    upsert_transaction(db_session, tx)

    count = db_session.execute(
        select(sa.func.count())
        .select_from(Transaction)
        .where(Transaction.pluggy_transaction_id == pluggy_id)
    ).scalar_one()
    assert count == 1


def test_two_identical_transactions_same_day_coexist(
    db_session: Session, account_id: int
) -> None:
    """Regressão da migration 0014: dois PIX recebidos de R$7 no mesmo dia, com a
    mesma descrição genérica, são transações DIFERENTES. Enquanto o fingerprint
    usava só a data, o segundo colidia com o primeiro e era engolido na ingestão."""
    from core.ingestion.normalize import compute_transaction_fingerprint

    manha = datetime(2026, 1, 5, 14, 10, tzinfo=UTC)
    tarde = datetime(2026, 1, 5, 15, 56, tzinfo=UTC)
    ids = []
    for instante in (manha, tarde):
        fp = compute_transaction_fingerprint(
            "acc-fp-test", instante, Decimal("12.50"), Direction.OUT, "padaria do ze"
        )
        pluggy_id = uuid.uuid4()
        outcome = upsert_transaction(
            db_session,
            _tx(
                account_id=account_id,
                pluggy_transaction_id=pluggy_id,
                fingerprint=fp,
                occurred_at=instante,
            ),
        )
        assert outcome == "inserted"
        ids.append(pluggy_id)

    total = db_session.execute(
        select(sa.func.count())
        .select_from(Transaction)
        .where(Transaction.pluggy_transaction_id.in_(ids))
    ).scalar_one()
    assert total == 2  # <- era 1 antes da 0014
