from collections.abc import Iterator
from datetime import date, datetime
from types import TracebackType
from typing import Any, Self
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx

from jobs.pluggy.schemas import (
    PluggyAccount,
    PluggyAccountPage,
    PluggyInvestment,
    PluggyInvestmentPage,
    PluggyItem,
    PluggyTransaction,
    PluggyTransactionPage,
)

PLUGGY_BASE_URL = "https://api.pluggy.ai"


class PluggyAuthError(RuntimeError):
    pass


class PluggyClient:
    """Cliente HTTP para a API da Pluggy. Cuida só de autenticação e transporte —
    nenhuma normalização de domínio (direction, fingerprint) acontece aqui."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = PLUGGY_BASE_URL,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client or httpx.Client(base_url=base_url, timeout=30.0)
        self._api_key: str | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _authenticate(self) -> str:
        response = self._http.post(
            "/auth",
            json={
                "clientId": self._client_id,
                "clientSecret": self._client_secret,
                "nonExpiring": False,
            },
        )
        if response.status_code != 200:
            raise PluggyAuthError(
                f"Falha ao autenticar na Pluggy: {response.status_code} {response.text}"
            )
        api_key: str = response.json()["apiKey"]
        return api_key

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._api_key is None:
            self._api_key = self._authenticate()

        response = self._http.request(method, path, headers={"X-API-KEY": self._api_key}, **kwargs)
        if response.status_code == 403:
            # apiKey expira em 2h (curta duração de propósito, ver docs/arquitetura-app-financas.md §8).
            # Reautentica uma vez e tenta de novo antes de desistir.
            self._api_key = self._authenticate()
            response = self._http.request(
                method, path, headers={"X-API-KEY": self._api_key}, **kwargs
            )
        response.raise_for_status()
        return response

    def get_item(self, item_id: UUID | str) -> PluggyItem:
        response = self._request("GET", f"/items/{item_id}")
        return PluggyItem.model_validate(response.json())

    def list_accounts(self, item_id: UUID | str) -> list[PluggyAccount]:
        response = self._request("GET", "/accounts", params={"itemId": str(item_id)})
        return PluggyAccountPage.model_validate(response.json()).results

    def list_investments(self, item_id: UUID | str) -> list[PluggyInvestment]:
        """Sem paginação de propósito, igual `list_accounts`: a carteira de
        um usuário só cabe numa página só (a doc §3.2 cita 14 ativos como
        exemplo real)."""
        response = self._request("GET", "/investments", params={"itemId": str(item_id)})
        return PluggyInvestmentPage.model_validate(response.json()).results

    def list_transactions(
        self,
        account_id: UUID | str,
        *,
        cursor: str | None = None,
        created_at_from: datetime | None = None,
        date_from: date | None = None,
    ) -> PluggyTransactionPage:
        params: dict[str, str] = {"accountId": str(account_id)}
        if cursor is not None:
            params["after"] = cursor
        if created_at_from is not None:
            params["createdAtFrom"] = created_at_from.isoformat()
        if date_from is not None:
            params["dateFrom"] = date_from.isoformat()
        response = self._request("GET", "/v2/transactions", params=params)
        return PluggyTransactionPage.model_validate(response.json())

    def iter_transactions(
        self,
        account_id: UUID | str,
        *,
        created_at_from: datetime | None = None,
        date_from: date | None = None,
    ) -> Iterator[PluggyTransaction]:
        """`created_at_from` é o que torna o sync incremental barato: sem isso,
        cada sync diário repuxaria os 12 meses inteiros de novo.

        CUIDADO — verificado contra a API em 2026-08-23, o docstring anterior
        aqui afirmava o oposto: `createdAtFrom` filtra **estritamente** por
        quando a Pluggy criou o registro. Uma transação criada antes do cursor
        NUNCA volta, aconteça o que acontecer com ela depois. Experimento:
        pedimos `createdAtFrom` posterior à criação de 10 transações PENDING
        conhecidas — voltaram 0. Some-se a isso que a Pluggy nunca atualiza um
        registro no lugar (576 transações checadas em duas contas, todas com
        `updatedAt == createdAt`), e o sync incremental sozinho não tem como
        entregar uma mudança de status.

        Por isso `date_from` existe: filtra pela data da transação (parâmetro
        `dateFrom`), e é o que o sync usa pra reler uma janela recente a cada
        execução, independente do cursor. Ver `jobs/sync/run.py`.
        """
        cursor: str | None = None
        while True:
            page = self.list_transactions(
                account_id, cursor=cursor, created_at_from=created_at_from, date_from=date_from
            )
            yield from page.results
            if page.next is None:
                return
            cursor = _extract_cursor(page.next)
            if cursor is None:
                return


def _extract_cursor(next_value: str) -> str | None:
    """A Pluggy manda `next` como querystring relativa (ex: "?accountId=...&after=<token>"),
    não como o token puro. O SDK oficial em Node extrai o parâmetro `after` da mesma forma."""
    query = urlparse(next_value).query
    values = parse_qs(query).get("after")
    return values[0] if values else None
