from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.models import Investment, InvestmentSnapshot, SyncRun, Transaction
from core.models.transaction import TxStatus
from jobs.pluggy.client import PluggyClient
from jobs.sync.run import sync_item

ITEM_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT_ID = "22222222-2222-2222-2222-222222222222"
TX1_ID = "33333333-3333-3333-3333-333333333331"
TX2_ID = "33333333-3333-3333-3333-333333333332"


def _item_json() -> dict[str, Any]:
    return {
        "id": ITEM_ID,
        "connector": {"id": 200, "name": "MeuPluggy"},
        "status": "UPDATED",
        "executionStatus": "SUCCESS",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
        "lastUpdatedAt": "2026-01-01T00:00:00Z",
        "consentExpiresAt": "2026-06-01T00:00:00Z",
    }


def _accounts_json() -> dict[str, Any]:
    return {
        "page": 1,
        "total": 1,
        "totalPages": 1,
        "results": [
            {
                "id": ACCOUNT_ID,
                "itemId": ITEM_ID,
                "type": "BANK",
                "subtype": "CHECKING_ACCOUNT",
                "number": "00012345",
                "name": "Conta Corrente",
                "currencyCode": "BRL",
                "balance": "1000.00",
                "creditData": None,
            }
        ],
    }


def _transaction_json(tx_id: str, description: str) -> dict[str, Any]:
    return {
        "id": tx_id,
        "accountId": ACCOUNT_ID,
        "date": "2026-01-05T00:00:00Z",
        "description": description,
        "type": "DEBIT",
        "amount": "-12.50",
        "balance": "987.65",
        "currencyCode": "BRL",
        "category": "Eating out",
        "status": "POSTED",
    }


def _pluggy_client(handler: Callable[[httpx.Request], httpx.Response]) -> PluggyClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(base_url="https://api.pluggy.ai", transport=transport)
    return PluggyClient("client-id", "client-secret", http_client=http_client)


INVESTMENT_ID = "55555555-5555-5555-5555-555555555555"


def _investments_json(results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    results = results if results is not None else []
    return {"page": 1, "total": len(results), "totalPages": 1, "results": results}


def _investment_json() -> dict[str, Any]:
    return {
        "id": INVESTMENT_ID,
        "itemId": ITEM_ID,
        "type": "FIXED_INCOME",
        "subtype": "CDB",
        "name": "CDB 110% CDI",
        "balance": "5230.10",
        "status": "ACTIVE",
        "issuer": "Banco XP",
    }


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/auth":
        return httpx.Response(200, json={"apiKey": "key-1"})
    if request.url.path == f"/items/{ITEM_ID}":
        return httpx.Response(200, json=_item_json())
    if request.url.path == "/investments":
        return httpx.Response(200, json=_investments_json())
    if request.url.path == "/accounts":
        return httpx.Response(200, json=_accounts_json())
    if request.url.path == "/v2/transactions":
        # O fake distingue as duas passadas do sync, senão o teste não prova
        # nada sobre elas. `createdAtFrom` = "o que você criou desde o cursor"
        # (nada, no fake); `dateFrom` = releitura da janela recente.
        both = [
            _transaction_json(TX1_ID, "PADARIA DO ZE"),
            _transaction_json(TX2_ID, "UBER TRIP"),
        ]
        params = request.url.params
        if "createdAtFrom" in params:
            return httpx.Response(200, json={"results": [], "next": None})
        return httpx.Response(200, json={"results": both, "next": None})
    raise AssertionError(f"unexpected path {request.url.path}")


def _handler_with_investment(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/investments":
        return httpx.Response(200, json=_investments_json([_investment_json()]))
    return _handler(request)


def test_sync_item_upserts_investment_and_snapshot(db_session: Session) -> None:
    client = _pluggy_client(_handler_with_investment)

    result = sync_item(db_session, client, ITEM_ID, kind="FULL")
    assert result.investments_synced == 1

    investment = db_session.execute(
        select(Investment).where(Investment.pluggy_investment_id == INVESTMENT_ID)
    ).scalar_one()
    assert investment.name == "CDB 110% CDI"
    assert investment.is_active is True

    snapshot = db_session.execute(
        select(InvestmentSnapshot).where(InvestmentSnapshot.investment_id == investment.id)
    ).scalar_one()
    assert snapshot.balance == Decimal("5230.10")


def test_sync_item_inserts_accounts_and_transactions(db_session: Session) -> None:
    client = _pluggy_client(_handler)

    result = sync_item(db_session, client, ITEM_ID, kind="FULL")

    assert result.accounts_synced == 1
    assert result.tx_inserted == 2
    assert result.tx_updated == 0
    assert result.tx_duplicates == 0

    sync_run = db_session.get(SyncRun, result.sync_run_id)
    assert sync_run is not None
    assert sync_run.status == "SUCCESS"
    assert sync_run.finished_at is not None


def test_sync_item_twice_is_idempotent(db_session: Session) -> None:
    client = _pluggy_client(_handler)

    sync_item(db_session, client, ITEM_ID, kind="FULL")
    second = sync_item(db_session, client, ITEM_ID, kind="INCREMENTAL")

    assert second.tx_inserted == 0
    assert second.tx_updated == 2

    # conta só as transações deste teste — o banco de dev pode ter outras
    # linhas de execuções manuais anteriores, e a regra do projeto proíbe
    # DELETE em transaction, então o teste não pode assumir tabela vazia.
    total = db_session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.pluggy_transaction_id.in_([TX1_ID, TX2_ID]))
    ).scalar_one()
    assert total == 2


TX_PENDING_ID = "33333333-3333-3333-3333-333333333341"
TX_POSTED_ID = "33333333-3333-3333-3333-333333333342"


def _pending_then_posted_handler() -> Callable[[httpx.Request], httpx.Response]:
    """Reproduz o que a Pluggy faz de verdade (verificado contra a API em
    2026-08-23): ela NUNCA atualiza um registro no lugar — a transação
    liquidada chega como registro NOVO, com id novo e `createdAt` novo. Como
    descrição, valor e data não mudaram, o fingerprint é o mesmo.

    Antes de 2026-08-23 isso era descartado como "duplicate" e a linha PENDING
    ficava PENDING pra sempre no nosso banco, mesmo depois de liquidada — dinheiro
    gasto que nunca aparecia em "quanto gastei" (a mv_monthly_cashflow filtra
    status = POSTED) e que ficava inflando "compromissos futuros" eternamente.
    """
    state = {"liquidada": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/v2/transactions":
            return _handler(request)
        if state["liquidada"]:
            tx = _transaction_json(TX_POSTED_ID, "MERCADO CENTRAL")
            tx["status"] = "POSTED"
        else:
            tx = _transaction_json(TX_PENDING_ID, "MERCADO CENTRAL")
            tx["status"] = "PENDING"
        params = request.url.params
        if "createdAtFrom" in params and not state["liquidada"]:
            return httpx.Response(200, json={"results": [], "next": None})
        return httpx.Response(200, json={"results": [tx], "next": None})

    def toggle() -> None:
        state["liquidada"] = True

    handler.toggle = toggle  # type: ignore[attr-defined]
    return handler


def test_pending_becomes_posted_on_a_later_sync(db_session: Session) -> None:
    handler = _pending_then_posted_handler()
    client = _pluggy_client(handler)

    sync_item(db_session, client, ITEM_ID, kind="FULL")
    row = db_session.execute(
        select(Transaction).where(Transaction.pluggy_transaction_id == TX_PENDING_ID)
    ).scalar_one()
    assert row.status == TxStatus.PENDING

    handler.toggle()  # type: ignore[attr-defined]
    second = sync_item(db_session, client, ITEM_ID, kind="INCREMENTAL")

    # Chegou com id novo e mesmo fingerprint: não vira linha nova.
    assert second.tx_inserted == 0
    assert second.tx_duplicates >= 1
    assert (
        db_session.execute(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.pluggy_transaction_id.in_([TX_PENDING_ID, TX_POSTED_ID]))
        ).scalar_one()
        == 1
    )

    db_session.expire_all()
    row = db_session.execute(
        select(Transaction).where(Transaction.pluggy_transaction_id == TX_PENDING_ID)
    ).scalar_one()
    assert row.status == TxStatus.POSTED  # <- era isto que nunca acontecia


def test_full_sync_ignores_the_cursor(db_session: Session) -> None:
    """`kind="FULL"` tem que reler tudo. Até 2026-08-23 o `kind` era só gravado
    no `sync_run` e o cursor era consultado de qualquer jeito, então um "full"
    era um incremental disfarçado — e transações antigas fora da janela de
    releitura eram irrecuperáveis."""
    pedidos: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/transactions":
            pedidos.append(dict(request.url.params))
            return httpx.Response(200, json={"results": [], "next": None})
        return _handler(request)

    client = _pluggy_client(handler)
    sync_item(db_session, client, ITEM_ID, kind="INCREMENTAL")  # grava o cursor
    pedidos.clear()
    sync_item(db_session, client, ITEM_ID, kind="FULL")

    assert pedidos, "nenhuma busca de transação aconteceu"
    assert not any("createdAtFrom" in p for p in pedidos), (
        "sync FULL não pode usar o cursor incremental"
    )
