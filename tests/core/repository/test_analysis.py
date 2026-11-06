import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from core.models import Account, Connection, Transaction
from core.models.transaction import Direction, TxStatus
from core.repository.analysis import load_matchable_transactions
from tests.helpers import as_instant


def _card(session: Session) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()
    account = Account(
        connection_id=connection.id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=f"acc-fp-matchable-{uuid.uuid4()}",
        type="CREDIT",
        currency_code="BRL",
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _transaction(session: Session, account_id: int, *, direction: Direction) -> int:
    transaction = Transaction(
        account_id=account_id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-matchable-{uuid.uuid4()}",
        description="SUA ACADEMIA",
        description_norm="sua academia",
        amount=Decimal("119.90") if direction is Direction.IN else Decimal("-119.90"),
        amount_abs=Decimal("119.90"),
        direction=direction,
        is_card_credit=direction is Direction.IN,
        currency_code="BRL",
        date=date(2030, 5, 10),
        occurred_at=as_instant(date(2030, 5, 10)),
        accrual_date=date(2030, 5, 10),
        status=TxStatus.POSTED,
        raw={},
    )
    session.add(transaction)
    session.flush()
    return transaction.id


def test_matchable_pool_leaves_out_card_credits(db_session: Session) -> None:
    """Estorno e "pula compra" não são receita (regra de domínio 11): não podem
    casar com um `planned_item` de renda nem virar receita recorrente."""
    card = _card(db_session)
    purchase = _transaction(db_session, card, direction=Direction.OUT)
    credit = _transaction(db_session, card, direction=Direction.IN)

    ids = {t.transaction_id for t in load_matchable_transactions(db_session)}

    assert purchase in ids
    assert credit not in ids
