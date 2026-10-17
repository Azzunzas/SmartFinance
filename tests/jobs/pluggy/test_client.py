from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from jobs.pluggy.client import PluggyClient

ITEM_ID = "11111111-1111-1111-1111-111111111111"
ACCOUNT_ID = "22222222-2222-2222-2222-222222222222"
TX1_ID = "33333333-3333-3333-3333-333333333331"
TX2_ID = "33333333-3333-3333-3333-333333333332"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> PluggyClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(base_url="https://api.pluggy.ai", transport=transport)
    return PluggyClient("client-id", "client-secret", http_client=http_client)


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


def _transaction_json(tx_id: str) -> dict[str, Any]:
    return {
        "id": tx_id,
        "accountId": ACCOUNT_ID,
        "date": "2026-01-05T00:00:00Z",
        "description": "PADARIA DO ZE",
        "type": "DEBIT",
        "amount": "-12.50",
        "balance": "987.65",
        "currencyCode": "BRL",
        "category": "Eating out",
        "status": "POSTED",
    }


def test_get_item_authenticates_and_parses() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "key-1"})
        if request.url.path == f"/items/{ITEM_ID}":
            assert request.headers["X-API-KEY"] == "key-1"
            return httpx.Response(200, json=_item_json())
        raise AssertionError(f"unexpected path {request.url.path}")

    client = _client(handler)
    item = client.get_item(ITEM_ID)

    assert item.status == "UPDATED"
    assert item.connector.name == "MeuPluggy"
    assert calls == ["/auth", f"/items/{ITEM_ID}"]


def test_list_accounts_unwraps_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "key-1"})
        if request.url.path == "/accounts":
            assert request.url.params["itemId"] == ITEM_ID
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total": 1,
                    "totalPages": 1,
                    "results": [
                        {
                            "id": ACCOUNT_ID,
                            "itemId": ITEM_ID,
                            "type": "BANK",
                            "subtype": "CHECKING_ACCOUNT",
                            "number": "0001",
                            "name": "Conta Corrente",
                            "currencyCode": "BRL",
                            "balance": "1234.56",
                            "creditData": None,
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    client = _client(handler)
    accounts = client.list_accounts(ITEM_ID)

    assert len(accounts) == 1
    assert accounts[0].balance == Decimal("1234.56")
    assert accounts[0].credit_data is None


def test_list_investments_unwraps_page_and_keeps_extra_fields() -> None:
    investment_id = "44444444-4444-4444-4444-444444444444"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "key-1"})
        if request.url.path == "/investments":
            assert request.url.params["itemId"] == ITEM_ID
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total": 1,
                    "totalPages": 1,
                    "results": [
                        {
                            "id": investment_id,
                            "itemId": ITEM_ID,
                            "type": "FIXED_INCOME",
                            "subtype": "CDB",
                            "name": "CDB 110% CDI",
                            "balance": "5230.10",
                            "status": "ACTIVE",
                            "issuer": "Banco XP",
                            # campo não modelado no schema — precisa sobreviver
                            # ao model_dump() por causa do extra="allow".
                            "annualRate": "12.5",
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    client = _client(handler)
    investments = client.list_investments(ITEM_ID)

    assert len(investments) == 1
    investment = investments[0]
    assert investment.name == "CDB 110% CDI"
    assert investment.balance == Decimal("5230.10")
    assert investment.issuer == "Banco XP"
    assert investment.model_dump(mode="json", by_alias=True)["annualRate"] == "12.5"


def test_iter_transactions_follows_cursor() -> None:
    pages: dict[str | None, dict[str, Any]] = {
        None: {
            "results": [_transaction_json(TX1_ID)],
            "next": f"?accountId={ACCOUNT_ID}&after=cursor-1",
        },
        "cursor-1": {
            "results": [_transaction_json(TX2_ID)],
            "next": None,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "key-1"})
        if request.url.path == "/v2/transactions":
            after = request.url.params.get("after")
            return httpx.Response(200, json=pages[after])
        raise AssertionError(f"unexpected path {request.url.path}")

    client = _client(handler)
    transactions = list(client.iter_transactions(ACCOUNT_ID))

    assert [str(t.id) for t in transactions] == [TX1_ID, TX2_ID]


def test_iter_transactions_sends_created_at_from_as_filter() -> None:
    seen_params: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth":
            return httpx.Response(200, json={"apiKey": "key-1"})
        if request.url.path == "/v2/transactions":
            seen_params.append(request.url.params.get("createdAtFrom"))
            return httpx.Response(200, json={"results": [], "next": None})
        raise AssertionError(f"unexpected path {request.url.path}")

    client = _client(handler)
    since = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
    list(client.iter_transactions(ACCOUNT_ID, created_at_from=since))

    assert seen_params == [since.isoformat()]


def test_expired_api_key_triggers_single_reauth() -> None:
    auth_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal auth_calls
        if request.url.path == "/auth":
            auth_calls += 1
            return httpx.Response(200, json={"apiKey": f"key-{auth_calls}"})
        if request.url.path == f"/items/{ITEM_ID}":
            if request.headers["X-API-KEY"] == "key-1":
                return httpx.Response(403, json={"code": 403, "message": "expired"})
            return httpx.Response(200, json=_item_json())
        raise AssertionError(f"unexpected path {request.url.path}")

    client = _client(handler)
    item = client.get_item(ITEM_ID)

    assert item.status == "UPDATED"
    assert auth_calls == 2
