import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.models import Account, Connection, CreditCardBill
from core.repository.bills import BillUpsert, list_bills, load_upcoming_bills, upsert_bill


def _card(session: Session, *, include_in_analysis: bool = True) -> int:
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
        fingerprint=f"acc-fp-bill-{uuid.uuid4()}",
        type="CREDIT",
        subtype="CREDIT_CARD",
        currency_code="BRL",
        include_in_analysis=include_in_analysis,
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _bill(
    account_id: int,
    *,
    due_date: date,
    total: str,
    pluggy_bill_id: uuid.UUID | None = None,
) -> BillUpsert:
    return BillUpsert(
        account_id=account_id,
        pluggy_bill_id=pluggy_bill_id or uuid.uuid4(),
        due_date=due_date,
        close_date=None,
        total_amount=Decimal(total),
        minimum_payment=None,
        finance_charges_total=Decimal(0),
        currency_code="BRL",
        raw={},
    )


def test_upsert_bill_updates_the_same_row(db_session: Session) -> None:
    card = _card(db_session)
    bill_id = uuid.uuid4()

    first = upsert_bill(
        db_session, _bill(card, due_date=date(2026, 11, 10), total="100.00", pluggy_bill_id=bill_id)
    )
    second = upsert_bill(
        db_session, _bill(card, due_date=date(2026, 11, 10), total="120.00", pluggy_bill_id=bill_id)
    )

    assert first == second
    assert [b.total_amount for b in list_bills(db_session, account_id=card)] == [Decimal("120.00")]


def test_list_bills_keeps_one_bill_per_card_per_due_month(db_session: Session) -> None:
    """A Pluggy troca o `billId` de provisório para definitivo, às vezes com
    ajuste de vencimento. A linha do id antigo para de ser atualizada; a que o
    sync viu por último é a que vale."""
    card = _card(db_session)
    definitive = upsert_bill(db_session, _bill(card, due_date=date(2026, 11, 10), total="2517.59"))
    provisional = upsert_bill(db_session, _bill(card, due_date=date(2026, 11, 12), total="2400.00"))
    db_session.execute(
        sa.update(CreditCardBill)
        .where(CreditCardBill.id == provisional)
        .values(updated_at=sa.func.now() - sa.text("interval '1 day'"))
    )

    bills = list_bills(db_session, account_id=card)

    assert [b.id for b in bills] == [definitive]


def test_list_bills_orders_by_due_date_and_respects_limit(db_session: Session) -> None:
    card = _card(db_session)
    for month, total in [(9, "10.00"), (11, "30.00"), (10, "20.00")]:
        upsert_bill(db_session, _bill(card, due_date=date(2026, month, 10), total=total))

    bills = list_bills(db_session, account_id=card, limit=2)

    assert [b.due_date for b in bills] == [date(2026, 11, 10), date(2026, 10, 10)]


def test_load_upcoming_bills_skips_cards_excluded_from_analysis(db_session: Session) -> None:
    included = _card(db_session)
    excluded = _card(db_session, include_in_analysis=False)
    upsert_bill(db_session, _bill(included, due_date=date(2031, 1, 10), total="11.11"))
    upsert_bill(db_session, _bill(excluded, due_date=date(2031, 1, 10), total="22.22"))

    amounts = {b.amount for b in load_upcoming_bills(db_session) if b.due_date.year == 2031}

    assert amounts == {Decimal("11.11")}
