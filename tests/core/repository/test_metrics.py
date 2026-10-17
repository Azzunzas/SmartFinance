import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from core.analysis.health import assess_financial_health
from core.analysis.planned_matching import PlannedKind
from core.models import (
    Account,
    BalanceSnapshot,
    Category,
    Connection,
    Investment,
    InvestmentSnapshot,
    PlannedItem,
    Transaction,
    TransactionClassification,
)
from core.models.transaction import Direction, TxStatus
from core.repository.analysis import refresh_monthly_cashflow
from core.repository.metrics import (
    NetWorthPoint,
    load_category_spend,
    load_health_inputs,
    load_monthly_cashflow,
    load_net_worth_history,
)
from tests.helpers import as_instant


def _account(
    session: Session,
    *,
    type: str = "BANK",
    is_own: bool = True,
    include_in_analysis: bool = True,
) -> int:
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
        fingerprint=f"acc-fp-cashflow-{uuid.uuid4()}",
        type=type,
        currency_code="BRL",
        is_own=is_own,
        include_in_analysis=include_in_analysis,
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _balance_snapshot(session: Session, account_id: int, *, day: date, balance: str) -> None:
    session.add(
        BalanceSnapshot(
            account_id=account_id,
            captured_at=datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
            balance=Decimal(balance),
        )
    )
    session.flush()


def _investment(session: Session, *, is_active: bool = True) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()

    investment = Investment(
        connection_id=connection.id,
        pluggy_investment_id=uuid.uuid4(),
        name="CDB teste",
        type="FIXED_INCOME",
        status="ACTIVE",
        is_active=is_active,
        raw={},
    )
    session.add(investment)
    session.flush()
    return investment.id


def _investment_snapshot(session: Session, investment_id: int, *, day: date, balance: str) -> None:
    session.add(
        InvestmentSnapshot(
            investment_id=investment_id,
            captured_at=datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
            balance=Decimal(balance),
        )
    )
    session.flush()


def _transaction(
    session: Session, account_id: int, *, accrual_date: date, direction: Direction, amount: str
) -> int:
    signed = Decimal(amount) if direction is Direction.IN else -Decimal(amount)
    transaction = Transaction(
        account_id=account_id,
        pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-cashflow-{uuid.uuid4()}",
        description="TESTE CASHFLOW",
        description_norm="teste cashflow",
        amount=signed,
        amount_abs=Decimal(amount),
        direction=direction,
        currency_code="BRL",
        date=accrual_date,
        occurred_at=as_instant(accrual_date),
        accrual_date=accrual_date,
        status=TxStatus.POSTED,
        raw={},
    )
    session.add(transaction)
    session.flush()
    return transaction.id


def _classify(
    session: Session,
    transaction_id: int,
    *,
    category_id: int | None = None,
    is_internal_transfer: bool = False,
    is_card_payment: bool = False,
    exclude_from_analysis: bool = False,
) -> None:
    session.add(
        TransactionClassification(
            transaction_id=transaction_id,
            category_id_auto=category_id,
            is_internal_transfer_auto=is_internal_transfer,
            is_card_payment_auto=is_card_payment,
            exclude_from_analysis=exclude_from_analysis,
        )
    )
    session.flush()


def _category_id(session: Session, name: str) -> int:
    return session.execute(sa.select(Category.id).where(Category.name == name)).scalar_one()


# Datas no futuro distante (2030) de propósito: garante que nenhum dado real
# sincronizado (2025/2026) cai nesses períodos, então os testes não dependem
# do estado do banco de dev — mesma lição de "antes vs. depois" já usada em
# test_metrics.py, só que aqui dá pra isolar de vez escolhendo um intervalo
# que não existe em produção.


def test_load_monthly_cashflow_zero_fills_periods_without_data(db_session: Session) -> None:
    records = load_monthly_cashflow(
        db_session, reference_date=date(2030, 6, 15), months=3, order="asc"
    )

    assert [r.period for r in records] == ["2030-04", "2030-05", "2030-06"]
    for record in records:
        assert record.total_in == 0
        assert record.total_out == 0
        assert record.net == 0


def test_load_monthly_cashflow_aggregates_real_transactions(db_session: Session) -> None:
    account_id = _account(db_session)
    _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 1, 10),
        direction=Direction.OUT,
        amount="150.00",
    )
    _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 1, 20),
        direction=Direction.IN,
        amount="1000.00",
    )
    refresh_monthly_cashflow(db_session)

    records = load_monthly_cashflow(
        db_session, reference_date=date(2030, 1, 25), months=1, order="asc"
    )

    assert len(records) == 1
    record = records[0]
    assert record.period == "2030-01"
    assert record.total_in == Decimal("1000.00")
    assert record.total_out == Decimal("150.00")
    assert record.net == Decimal("850.00")


def test_load_monthly_cashflow_order_desc_reverses_asc(db_session: Session) -> None:
    asc = load_monthly_cashflow(db_session, reference_date=date(2030, 9, 1), months=4, order="asc")
    desc = load_monthly_cashflow(
        db_session, reference_date=date(2030, 9, 1), months=4, order="desc"
    )

    assert [r.period for r in desc] == [r.period for r in reversed(asc)]
    assert [r.period for r in asc] == ["2030-06", "2030-07", "2030-08", "2030-09"]


# `load_net_worth_history` soma TODAS as contas/investimentos do banco (não
# só os do teste) porque o forward-fill não tem validade — um snapshot real
# de 2026 continua sendo "o último valor conhecido" pra qualquer dia futuro
# que a gente pedir, inclusive 2030. Por isso os testes abaixo usam
# "antes vs. depois" (mesma lição de test_overview_computes_net_worth em
# tests/api/routers/test_metrics.py), não isolamento por data.


def _by_date(records: list[NetWorthPoint]) -> dict[date, Decimal]:
    return {r.date: r.net_worth for r in records}


def test_load_net_worth_history_zero_before_first_snapshot(db_session: Session) -> None:
    before = _by_date(load_net_worth_history(db_session, reference_date=date(2030, 3, 10), days=5))

    account_id = _account(db_session)
    _balance_snapshot(db_session, account_id, day=date(2030, 3, 20), balance="1000.00")

    after = _by_date(load_net_worth_history(db_session, reference_date=date(2030, 3, 10), days=5))

    # snapshot só existe em 20/03 — nenhum dia desse intervalo (06 a 10) pode
    # ter mudado, mesmo o snapshot já existindo no banco.
    for day in before:
        assert after[day] == before[day]


def test_load_net_worth_history_forward_fills_between_snapshots(db_session: Session) -> None:
    before = _by_date(load_net_worth_history(db_session, reference_date=date(2030, 4, 12), days=10))

    account_id = _account(db_session)
    _balance_snapshot(db_session, account_id, day=date(2030, 4, 5), balance="1000.00")
    _balance_snapshot(db_session, account_id, day=date(2030, 4, 10), balance="1200.00")

    after = _by_date(load_net_worth_history(db_session, reference_date=date(2030, 4, 12), days=10))
    diff = {day: after[day] - before[day] for day in before}

    assert diff[date(2030, 4, 3)] == 0  # antes do primeiro snapshot
    assert diff[date(2030, 4, 5)] == Decimal("1000.00")  # dia do 1º snapshot
    assert diff[date(2030, 4, 7)] == Decimal("1000.00")  # forward-fill, sem sync nesse dia
    assert diff[date(2030, 4, 10)] == Decimal("1200.00")  # dia do 2º snapshot
    assert diff[date(2030, 4, 12)] == Decimal("1200.00")  # forward-fill até hoje


def test_load_net_worth_history_combines_bank_credit_and_investments(
    db_session: Session,
) -> None:
    day = date(2030, 5, 15)
    before = _by_date(load_net_worth_history(db_session, reference_date=day, days=1))

    bank_id = _account(db_session, type="BANK")
    credit_id = _account(db_session, type="CREDIT")
    excluded_id = _account(db_session, type="BANK", include_in_analysis=False)
    investment_id = _investment(db_session, is_active=True)
    inactive_investment_id = _investment(db_session, is_active=False)

    _balance_snapshot(db_session, bank_id, day=day, balance="2000.00")
    _balance_snapshot(db_session, credit_id, day=day, balance="500.00")
    _balance_snapshot(db_session, excluded_id, day=day, balance="9999.00")
    _investment_snapshot(db_session, investment_id, day=day, balance="300.00")
    _investment_snapshot(db_session, inactive_investment_id, day=day, balance="7777.00")

    after = _by_date(load_net_worth_history(db_session, reference_date=day, days=1))

    # 2000 (bank) + 300 (investimento ativo) - 500 (fatura) — conta excluída
    # e investimento inativo não entram
    assert after[day] - before[day] == Decimal("1800.00")


def test_load_category_spend_groups_by_category(db_session: Session) -> None:
    account_id = _account(db_session)
    food_id = _category_id(db_session, "Alimentação")

    tx1 = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 7, 5),
        direction=Direction.OUT,
        amount="50.00",
    )
    tx2 = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 7, 10),
        direction=Direction.OUT,
        amount="30.00",
    )
    _classify(db_session, tx1, category_id=food_id)
    _classify(db_session, tx2, category_id=food_id)
    db_session.get_one(Transaction, tx1).merchant_name = "Mercado A"
    db_session.get_one(Transaction, tx2).merchant_name = "Mercado B"
    db_session.flush()

    records = load_category_spend(db_session, "2030-07")

    assert len(records) == 1
    assert records[0].category_id == food_id
    assert records[0].name == "Alimentação"
    assert records[0].total == Decimal("80.00")
    assert [(detail.name, detail.total) for detail in records[0].details] == [
        ("Mercado A", Decimal("50.00")),
        ("Mercado B", Decimal("30.00")),
    ]


def test_load_category_spend_falls_back_to_sem_categoria(db_session: Session) -> None:
    account_id = _account(db_session)
    sem_categoria_id = _category_id(db_session, "Sem categoria")

    tx = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 8, 5),
        direction=Direction.OUT,
        amount="12.00",
    )
    _classify(db_session, tx, category_id=None)

    records = load_category_spend(db_session, "2030-08")

    assert len(records) == 1
    assert records[0].category_id == sem_categoria_id
    assert records[0].name == "Sem categoria"
    assert records[0].total == Decimal("12.00")


def test_load_category_spend_excludes_transfers_payments_and_excluded(
    db_session: Session,
) -> None:
    account_id = _account(db_session)
    shopping_id = _category_id(db_session, "Compras")

    internal_transfer = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 9, 5),
        direction=Direction.OUT,
        amount="100.00",
    )
    card_payment = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 9, 6),
        direction=Direction.OUT,
        amount="200.00",
    )
    excluded = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 9, 7),
        direction=Direction.OUT,
        amount="300.00",
    )
    real_spend = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 9, 8),
        direction=Direction.OUT,
        amount="40.00",
    )
    _classify(db_session, internal_transfer, category_id=shopping_id, is_internal_transfer=True)
    _classify(db_session, card_payment, category_id=shopping_id, is_card_payment=True)
    _classify(db_session, excluded, category_id=shopping_id, exclude_from_analysis=True)
    _classify(db_session, real_spend, category_id=shopping_id)

    records = load_category_spend(db_session, "2030-09")

    assert len(records) == 1
    assert records[0].total == Decimal("40.00")


def test_load_category_spend_ignores_income_and_empty_period(db_session: Session) -> None:
    account_id = _account(db_session)
    income_id = _category_id(db_session, "Renda")

    tx = _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 10, 5),
        direction=Direction.IN,
        amount="1500.00",
    )
    _classify(db_session, tx, category_id=income_id)

    assert load_category_spend(db_session, "2030-10") == []
    assert load_category_spend(db_session, "2030-11") == []


def test_load_health_inputs_excludes_the_current_month(db_session: Session) -> None:
    """A decisão que mais muda número: em 15/06, junho está pela metade.
    Entrar na média puxaria o burn rate pra baixo e inflaria o runway."""
    account_id = _account(db_session)
    _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 5, 10),
        direction=Direction.OUT,
        amount="900.00",
    )
    _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 6, 3),
        direction=Direction.OUT,
        amount="30.00",
    )
    refresh_monthly_cashflow(db_session)

    inputs = load_health_inputs(db_session, reference_date=date(2030, 6, 15), months=3)

    periods = [m.period for m in inputs.months]
    assert "2030-06" not in periods
    assert periods == ["2030-05"]


def test_load_health_inputs_does_not_zero_fill_missing_months(db_session: Session) -> None:
    """Oposto deliberado de `load_monthly_cashflow`: mês ausente da view é
    mês sem sync, não mês sem gasto. Zerar dividiria por 3 um total que só
    tem 1 mês de verdade, e o burn rate sairia 1/3 do real."""
    account_id = _account(db_session)
    _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 5, 10),
        direction=Direction.OUT,
        amount="900.00",
    )
    refresh_monthly_cashflow(db_session)

    inputs = load_health_inputs(db_session, reference_date=date(2030, 6, 15), months=3)

    assert len(inputs.months) == 1
    assert assess_financial_health(inputs).burn_rate == Decimal("900.00")


def test_load_health_inputs_sums_planned_items_in_effect_by_kind(db_session: Session) -> None:
    db_session.add(
        PlannedItem(
            name="aluguel teste",
            kind=PlannedKind.FIXED_EXPENSE,
            expected_amount=Decimal("1200.00"),
            valid_from=date(2030, 1, 1),
        )
    )
    db_session.add(
        PlannedItem(
            name="plano antigo teste",
            kind=PlannedKind.FIXED_EXPENSE,
            expected_amount=Decimal("500.00"),
            valid_from=date(2029, 1, 1),
            valid_to=date(2029, 12, 31),
        )
    )
    db_session.flush()

    inputs = load_health_inputs(db_session, reference_date=date(2030, 6, 15), months=3)

    # O item vencido em 2029 não entra; só o vigente em 15/06/2030.
    assert inputs.planned_fixed_expense == Decimal("1200.00")


def test_month_without_any_income_reports_zero_not_null(db_session: Session) -> None:
    """Regressão da migration 0017. `SUM(x) FILTER (...)` devolve NULL, não
    zero, quando nada casa o filtro — e num mês só de saídas isso derrubava
    `GET /api/metrics/cashflow` com 500 (`total_in` é `Decimal`, não
    `Decimal | None`) e quebrava o burn rate com `TypeError`.

    Nunca estourou em produção porque todo mês do banco real tem entrada e
    saída. Falha sem o COALESCE, passa com ele."""
    account_id = _account(db_session)
    _transaction(
        db_session,
        account_id,
        accrual_date=date(2030, 3, 10),
        direction=Direction.OUT,
        amount="80.00",
    )
    refresh_monthly_cashflow(db_session)

    records = load_monthly_cashflow(
        db_session, reference_date=date(2030, 3, 20), months=1, order="asc"
    )
    assert records[0].total_in == Decimal("0")

    inputs = load_health_inputs(db_session, reference_date=date(2030, 4, 5), months=1)
    assert assess_financial_health(inputs).savings_rate is None
