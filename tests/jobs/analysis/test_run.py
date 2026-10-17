import datetime as _dt
import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.models import (
    Account,
    Connection,
    PlannedItem,
    PlannedItemMatch,
    PlannedItemRule,
    Transaction,
    TransactionClassification,
)
from core.models.transaction import Direction, TxStatus
from jobs.analysis.run import run_analysis
from tests.helpers import as_instant


def _as_instant(value: _dt.date | _dt.datetime) -> _dt.datetime:
    """`transaction.occurred_at` é NOT NULL desde a migration 0014 (o
    fingerprint depende do horário). Testes que só se importam com o dia
    civil usam meia-noite UTC dele."""
    if isinstance(value, _dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
    return _dt.datetime.combine(value, _dt.time(), tzinfo=_dt.UTC)


def _account(session: Session, connection_id: int) -> int:
    account = Account(
        connection_id=connection_id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=f"acc-fp-{uuid.uuid4()}",
        type="BANK",
        currency_code="BRL",
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _transaction(
    session: Session,
    account_id: int,
    *,
    amount: Decimal,
    direction: Direction,
    pluggy_category: str | None,
    day: int = 5,
) -> int:
    transaction = Transaction(
        account_id=account_id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-{uuid.uuid4()}",
        description="TESTE",
        description_norm="teste",
        amount=amount,
        amount_abs=abs(amount),
        direction=direction,
        currency_code="BRL",
        date=date(2026, 1, day),
        occurred_at=as_instant(date(2026, 1, day)),
        accrual_date=date(2026, 1, day),
        status=TxStatus.POSTED,
        pluggy_category=pluggy_category,
        raw={},
    )
    session.add(transaction)
    session.flush()
    return transaction.id


def test_run_analysis_classifies_transfer_payment_and_category(db_session: Session) -> None:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()

    account_a = _account(db_session, connection.id)
    account_b = _account(db_session, connection.id)

    transfer_out = _transaction(
        db_session, account_a, amount=Decimal("-100.00"), direction=Direction.OUT,
        pluggy_category=None,
    )
    transfer_in = _transaction(
        db_session, account_b, amount=Decimal("100.00"), direction=Direction.IN,
        pluggy_category=None,
    )
    card_payment = _transaction(
        db_session, account_a, amount=Decimal("-50.00"), direction=Direction.OUT,
        pluggy_category="Credit card payment",
    )
    groceries = _transaction(
        db_session, account_a, amount=Decimal("-30.00"), direction=Direction.OUT,
        pluggy_category="Groceries",
    )

    # run_analysis processa a tabela inteira de propósito (não é incremental)
    # — o banco de dev já tem outras transações reais, então não dá pra
    # assumir totais fixos aqui. Confere só a classificação das transações
    # que este teste criou.
    run_analysis(db_session)

    def classification(tx_id: int) -> TransactionClassification:
        return db_session.execute(
            sa.select(TransactionClassification).where(
                TransactionClassification.transaction_id == tx_id
            )
        ).scalar_one()

    assert classification(transfer_out).is_internal_transfer is True
    assert classification(transfer_out).counterpart_tx_id == transfer_in
    assert classification(transfer_in).is_internal_transfer is True
    assert classification(card_payment).is_card_payment is True
    groceries_row = classification(groceries)
    assert groceries_row.is_internal_transfer is False
    assert groceries_row.is_card_payment is False
    assert groceries_row.category_id is not None


def test_run_analysis_twice_is_idempotent(db_session: Session) -> None:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()
    account_a = _account(db_session, connection.id)
    account_b = _account(db_session, connection.id)
    _transaction(
        db_session, account_a, amount=Decimal("-100.00"), direction=Direction.OUT,
        pluggy_category=None,
    )
    _transaction(
        db_session, account_b, amount=Decimal("100.00"), direction=Direction.IN,
        pluggy_category=None,
    )

    first = run_analysis(db_session)
    second = run_analysis(db_session)

    assert first == second


def test_run_analysis_persists_planned_item_matches(db_session: Session) -> None:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()
    account = _account(db_session, connection.id)

    planned_item = PlannedItem(
        name="Mercado",
        kind="VARIABLE_BUDGET",
        expected_amount=Decimal("500.00"),
        valid_from=date(2026, 1, 1),
    )
    db_session.add(planned_item)
    db_session.flush()
    db_session.add(
        PlannedItemRule(
            planned_item_id=planned_item.id, match_type="CONTAINS", pattern="mercado"
        )
    )
    db_session.flush()

    matching_tx = Transaction(
        account_id=account,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-{uuid.uuid4()}",
        description="MERCADO CENTRAL",
        description_norm="mercado central",
        amount=Decimal("-80.00"),
        amount_abs=Decimal("80.00"),
        direction=Direction.OUT,
        currency_code="BRL",
        date=date(2026, 1, 10),
        occurred_at=as_instant(date(2026, 1, 10)),
        accrual_date=date(2026, 1, 10),
        status=TxStatus.POSTED,
        raw={},
    )
    db_session.add(matching_tx)
    db_session.flush()

    run_analysis(db_session)

    match = db_session.execute(
        sa.select(PlannedItemMatch).where(
            PlannedItemMatch.planned_item_id == planned_item.id,
            PlannedItemMatch.transaction_id == matching_tx.id,
        )
    ).scalar_one()
    assert match.period == "2026-01"
    assert match.matched_amount == Decimal("80.00")
    assert match.source == "AUTO"


def test_run_analysis_twice_does_not_duplicate_matches(db_session: Session) -> None:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()
    account = _account(db_session, connection.id)

    planned_item = PlannedItem(
        name="Aluguel",
        kind="FIXED_EXPENSE",
        expected_amount=Decimal("1500.00"),
        valid_from=date(2026, 1, 1),
    )
    db_session.add(planned_item)
    db_session.flush()
    db_session.add(
        PlannedItemRule(
            planned_item_id=planned_item.id, match_type="CONTAINS", pattern="aluguel"
        )
    )
    db_session.flush()
    db_session.add(
        Transaction(
            account_id=account,
            pluggy_transaction_id=uuid.uuid4(),
            fingerprint=f"tx-fp-{uuid.uuid4()}",
            description="ALUGUEL IMOB",
            description_norm="aluguel imob",
            amount=Decimal("-1500.00"),
            amount_abs=Decimal("1500.00"),
            direction=Direction.OUT,
            currency_code="BRL",
            date=date(2026, 1, 5),
            occurred_at=as_instant(date(2026, 1, 5)),
            accrual_date=date(2026, 1, 5),
            status=TxStatus.POSTED,
            raw={},
        )
    )
    db_session.flush()

    run_analysis(db_session)
    run_analysis(db_session)

    count = db_session.execute(
        sa.select(sa.func.count())
        .select_from(PlannedItemMatch)
        .where(PlannedItemMatch.planned_item_id == planned_item.id)
    ).scalar_one()
    assert count == 1
