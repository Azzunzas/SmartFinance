import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core.models import (
    Account,
    Connection,
    Investment,
    InvestmentSnapshot,
    PlannedItem,
    PlannedItemMatch,
    Transaction,
)
from core.models.transaction import Direction, TxStatus
from tests.helpers import as_instant


def _connection(session: Session) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()
    return connection.id


def _account(
    session: Session,
    connection_id: int,
    *,
    type: str,
    balance: str | None,
    is_own: bool = True,
    include_in_analysis: bool = True,
) -> int:
    account = Account(
        connection_id=connection_id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=f"acc-fp-metrics-{uuid.uuid4()}",
        type=type,
        currency_code="BRL",
        balance=Decimal(balance) if balance is not None else None,
        is_own=is_own,
        include_in_analysis=include_in_analysis,
        raw={},
    )
    session.add(account)
    session.flush()
    return account.id


def _active_investment(session: Session, connection_id: int, *, balance: str) -> int:
    investment = Investment(
        connection_id=connection_id,
        pluggy_investment_id=uuid.uuid4(),
        name="CDB",
        type="FIXED_INCOME",
        status="ACTIVE",
        is_active=True,
        raw={},
    )
    session.add(investment)
    session.flush()
    session.add(
        InvestmentSnapshot(
            investment_id=investment.id,
            captured_at=datetime(2026, 1, 1, tzinfo=UTC),
            balance=Decimal(balance),
        )
    )
    session.flush()
    return investment.id


def _overview(client: TestClient) -> dict[str, object]:
    response = client.get("/api/metrics/overview")
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


# O banco de dev usado por `db_session` já tem contas/investimentos reais
# (as 3 conexões sincronizadas nas fases anteriores) visíveis na mesma
# transação — /api/metrics/overview soma tudo, sem filtro por dono do teste.
# Por isso os testes comparam "antes vs. depois" em vez de valor absoluto,
# mesma lição já aprendida nos testes de matching/CRUD.


def test_overview_computes_net_worth(client: TestClient, db_session: Session) -> None:
    before = _overview(client)

    connection_id = _connection(db_session)
    _account(db_session, connection_id, type="BANK", balance="1000.00")
    _account(db_session, connection_id, type="CREDIT", balance="300.00")
    _active_investment(db_session, connection_id, balance="500.00")

    after = _overview(client)

    assert Decimal(str(after["open_credit_card_bill"])) - Decimal(
        str(before["open_credit_card_bill"])
    ) == Decimal("300.00")
    assert Decimal(str(after["investments_balance"])) - Decimal(
        str(before["investments_balance"])
    ) == Decimal("500.00")
    assert Decimal(str(after["net_worth"])) - Decimal(str(before["net_worth"])) == Decimal(
        "1200.00"
    )  # 1000 + 500 - 300
    assert len(after["accounts"]) == len(before["accounts"]) + 2  # type: ignore[arg-type]


def test_overview_survives_account_without_balance(
    client: TestClient, db_session: Session
) -> None:
    """`account.balance` é anulável (migration 0001) — a Pluggy pode não mandar
    saldo pra uma conta. Antes de 2026-08-23 isso derrubava o endpoint inteiro
    com `TypeError: Decimal + NoneType`: uma conta sem saldo apagava a tela de
    visão geral. Conta sem saldo contribui zero pro total, mas continua na
    lista com `balance: null`, pra diferença ficar visível."""
    before = _overview(client)

    connection_id = _connection(db_session)
    _account(db_session, connection_id, type="BANK", balance="1000.00")
    _account(db_session, connection_id, type="BANK", balance=None)

    after = _overview(client)

    assert Decimal(str(after["net_worth"])) - Decimal(str(before["net_worth"])) == Decimal(
        "1000.00"
    )
    assert len(after["accounts"]) == len(before["accounts"]) + 2  # type: ignore[arg-type]
    accounts = after["accounts"]
    assert isinstance(accounts, list)
    assert any(a["balance"] is None for a in accounts)


def test_overview_ignores_accounts_not_included_in_analysis(
    client: TestClient, db_session: Session
) -> None:
    before = _overview(client)

    connection_id = _connection(db_session)
    _account(db_session, connection_id, type="BANK", balance="1000.00")
    _account(
        db_session, connection_id, type="BANK", balance="9999.00", include_in_analysis=False
    )

    after = _overview(client)

    assert Decimal(str(after["net_worth"])) - Decimal(str(before["net_worth"])) == Decimal(
        "1000.00"
    )
    assert len(after["accounts"]) == len(before["accounts"]) + 1  # type: ignore[arg-type]


def test_overview_ignores_inactive_investments(client: TestClient, db_session: Session) -> None:
    before = _overview(client)

    connection_id = _connection(db_session)
    investment_id = _active_investment(db_session, connection_id, balance="500.00")
    investment = db_session.get_one(Investment, investment_id)
    investment.is_active = False
    db_session.flush()

    after = _overview(client)

    assert after["investments_balance"] == before["investments_balance"]


def _planned_item(
    session: Session,
    *,
    name: str,
    kind: str = "VARIABLE_BUDGET",
    expected_amount: str = "500.00",
    valid_from: date = date(2026, 1, 1),
    valid_to: date | None = None,
) -> int:
    item = PlannedItem(
        name=name,
        kind=kind,
        expected_amount=Decimal(expected_amount),
        valid_from=valid_from,
        valid_to=valid_to,
    )
    session.add(item)
    session.flush()
    return item.id


def test_planned_vs_actual_includes_item_with_zero_matches(
    client: TestClient, db_session: Session
) -> None:
    item_id = _planned_item(db_session, name="Lazer sem gasto")

    response = client.get("/api/metrics/planned-vs-actual", params={"period": "2026-03"})
    assert response.status_code == 200
    found = next(i for i in response.json() if i["planned_item_id"] == item_id)
    assert found["matched_amount"] == "0"
    assert found["expected_amount"] == "500.00"


def test_planned_vs_actual_sums_matches_only_for_requested_period(
    client: TestClient, db_session: Session
) -> None:
    item_id = _planned_item(db_session, name="Mercado com gasto")

    connection = Connection(
        pluggy_item_id=uuid.uuid4(), connector_id=200, connector_name="MeuPluggy",
        status="UPDATED", raw={},
    )
    db_session.add(connection)
    db_session.flush()
    account_id = _account(db_session, connection.id, type="BANK", balance="0.00")

    tx_march = Transaction(
        account_id=account_id, pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-pva-{uuid.uuid4()}", description="MERCADO",
        description_norm="mercado", amount=Decimal("-80.00"), amount_abs=Decimal("80.00"),
        direction=Direction.OUT, currency_code="BRL", date=date(2026, 3, 5),
        occurred_at=as_instant(date(2026, 3, 5)),
        accrual_date=date(2026, 3, 5), status=TxStatus.POSTED, raw={},
    )
    tx_april = Transaction(
        account_id=account_id, pluggy_transaction_id=uuid.uuid4(),
        fingerprint=f"tx-fp-pva2-{uuid.uuid4()}", description="MERCADO",
        description_norm="mercado", amount=Decimal("-30.00"), amount_abs=Decimal("30.00"),
        direction=Direction.OUT, currency_code="BRL", date=date(2026, 4, 5),
        occurred_at=as_instant(date(2026, 4, 5)),
        accrual_date=date(2026, 4, 5), status=TxStatus.POSTED, raw={},
    )
    db_session.add(tx_march)
    db_session.add(tx_april)
    db_session.flush()

    db_session.add(
        PlannedItemMatch(
            planned_item_id=item_id, period="2026-03", transaction_id=tx_march.id,
            matched_amount=Decimal("80.00"), source="AUTO",
        )
    )
    db_session.add(
        PlannedItemMatch(
            planned_item_id=item_id, period="2026-04", transaction_id=tx_april.id,
            matched_amount=Decimal("30.00"), source="AUTO",
        )
    )
    db_session.flush()

    response = client.get("/api/metrics/planned-vs-actual", params={"period": "2026-03"})
    found = next(i for i in response.json() if i["planned_item_id"] == item_id)
    assert found["matched_amount"] == "80.00"


def test_planned_vs_actual_excludes_items_outside_validity(
    client: TestClient, db_session: Session
) -> None:
    future_item_id = _planned_item(
        db_session, name="Ainda não começou", valid_from=date(2026, 6, 1)
    )
    ended_item_id = _planned_item(
        db_session, name="Já encerrado", valid_from=date(2025, 1, 1), valid_to=date(2025, 12, 31)
    )

    response = client.get("/api/metrics/planned-vs-actual", params={"period": "2026-03"})
    ids = {i["planned_item_id"] for i in response.json()}
    assert future_item_id not in ids
    assert ended_item_id not in ids


def test_planned_vs_actual_invalid_period_returns_422(client: TestClient) -> None:
    response = client.get("/api/metrics/planned-vs-actual", params={"period": "2026/03"})
    assert response.status_code == 422


def test_planned_vs_actual_defaults_to_current_month(client: TestClient) -> None:
    response = client.get("/api/metrics/planned-vs-actual")
    assert response.status_code == 200


def test_health_returns_all_five_metrics(client: TestClient) -> None:
    """Contrato completo: as cinco métricas da §5, a nota agregada e os dois
    componentes dela que não existiam como métrica própria. O front consome
    este payload inteiro — campo que sumir daqui quebra a tela."""
    response = client.get("/api/metrics/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "reference_months",
        "available_cash",
        "savings_rate",
        "burn_rate",
        "runway_months",
        "fixed_cost_monthly",
        "safety_margin",
        "score",
        "status",
        "bill_coverage",
        "net_worth_trend",
    }


def test_health_serializes_incalculable_metrics_as_null(client: TestClient) -> None:
    """Banco de teste sem mês fechado nenhum: o contrato precisa aceitar
    `null`, senão o Pydantic derruba a resposta com 500 na primeira
    instalação nova — que é exatamente quando ninguém está olhando o log."""
    response = client.get("/api/metrics/health")

    assert response.status_code == 200
    body = response.json()
    assert body["reference_months"] == []
    assert body["burn_rate"] is None
    assert body["runway_months"] is None
    assert body["score"] is None
    assert body["status"] is None
