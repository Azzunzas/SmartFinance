import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from pytest import MonkeyPatch
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from core.models import Connection, SyncRun
from jobs.sync.manual import claim_manual_sync, run_claimed_manual_sync
from jobs.sync.run import SyncResult


class _FakePluggyClient:
    def __init__(self, client_id: str, client_secret: str) -> None:
        pass

    def __enter__(self) -> _FakePluggyClient:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _aggregate_run() -> Select[tuple[SyncRun]]:
    """A linha que resume o sync manual inteiro.

    Desde 2026-08-24 as linhas por conexão e as de falha também são
    `kind="MANUAL"` — o que separa a agregada delas é não ter `connection_id`,
    porque ela cobre todas as conexões de uma vez.
    """
    return select(SyncRun).where(SyncRun.kind == "MANUAL", SyncRun.connection_id.is_(None))


def _connection(session: Session, item_id: uuid.UUID) -> Connection:
    connection = Connection(
        pluggy_item_id=item_id,
        connector_id=200,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    session.add(connection)
    session.flush()
    return connection


def test_manual_sync_aggregates_partial_result_and_deactivates_missing_item(
    db_session: Session, monkeypatch: MonkeyPatch
) -> None:
    valid_item_id = uuid.uuid4()
    missing_item_id = uuid.uuid4()
    _connection(db_session, valid_item_id)
    missing_connection = _connection(db_session, missing_item_id)

    @contextmanager
    def same_session() -> Iterator[Session]:
        yield db_session

    def sync_item(
        session: Session, client: object, item_id: str, *, kind: str = "INCREMENTAL"
    ) -> SyncResult:
        if item_id == str(missing_item_id):
            request = httpx.Request("GET", f"https://api.pluggy.ai/items/{item_id}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("item não encontrado", request=request, response=response)
        return SyncResult(
            sync_run_id=10,
            accounts_synced=2,
            tx_inserted=3,
            tx_updated=4,
            tx_duplicates=5,
            investments_synced=1,
        )

    monkeypatch.setenv("PLUGGY_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("jobs.sync.manual.create_session", same_session)
    monkeypatch.setattr("jobs.sync.manual.PluggyClient", _FakePluggyClient)
    monkeypatch.setattr("jobs.sync.manual.sync_item", sync_item)
    monkeypatch.setattr("jobs.sync.manual.run_analysis", lambda session: None)

    assert claim_manual_sync() is True
    run_claimed_manual_sync()

    db_session.refresh(missing_connection)
    assert missing_connection.is_active is False

    manual_run = db_session.scalar(_aggregate_run())
    assert manual_run is not None
    assert manual_run.status == "PARTIAL"
    assert manual_run.finished_at is not None
    assert manual_run.tx_inserted == 3
    assert manual_run.tx_updated == 4
    assert manual_run.tx_duplicates == 5
    assert manual_run.error_message == (
        "1 de 2 conexões falhou. 1 conexão indisponível na Pluggy foi desativada."
    )


def test_manual_sync_does_not_deactivate_item_for_unrelated_404(
    db_session: Session, monkeypatch: MonkeyPatch
) -> None:
    item_id = uuid.uuid4()
    connection = _connection(db_session, item_id)

    @contextmanager
    def same_session() -> Iterator[Session]:
        yield db_session

    def sync_item(
        session: Session, client: object, current_item_id: str, *, kind: str = "INCREMENTAL"
    ) -> SyncResult:
        request = httpx.Request("GET", "https://api.pluggy.ai/accounts/missing")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("conta não encontrada", request=request, response=response)

    monkeypatch.setenv("PLUGGY_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("jobs.sync.manual.create_session", same_session)
    monkeypatch.setattr("jobs.sync.manual.PluggyClient", _FakePluggyClient)
    monkeypatch.setattr("jobs.sync.manual.sync_item", sync_item)

    assert claim_manual_sync() is True
    run_claimed_manual_sync()

    db_session.refresh(connection)
    assert connection.is_active is True
    manual_run = db_session.scalar(_aggregate_run())
    assert manual_run is not None
    assert manual_run.status == "FAILED"


def test_each_connection_of_a_manual_sync_is_labeled_manual(
    db_session: Session, monkeypatch: MonkeyPatch
) -> None:
    """Sem esse rótulo, a tela não enxerga a execução que tem banco.

    A linha por conexão é a única que carrega `connection_id`; a agregada não
    tem banco pra apontar. Enquanto as linhas por conexão eram gravadas como
    `INCREMENTAL`, o Overview — que filtra por `kind=MANUAL` — só recebia a
    agregada e mostrava "Banco não identificado" em toda linha, sempre.
    """
    item_id = uuid.uuid4()
    _connection(db_session, item_id)
    kinds: list[str] = []

    @contextmanager
    def same_session() -> Iterator[Session]:
        yield db_session

    def sync_item(
        session: Session, client: object, current_item_id: str, *, kind: str = "INCREMENTAL"
    ) -> SyncResult:
        kinds.append(kind)
        return SyncResult(
            sync_run_id=10,
            accounts_synced=1,
            tx_inserted=0,
            tx_updated=0,
            tx_duplicates=0,
            investments_synced=0,
        )

    monkeypatch.setenv("PLUGGY_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("jobs.sync.manual.create_session", same_session)
    monkeypatch.setattr("jobs.sync.manual.PluggyClient", _FakePluggyClient)
    monkeypatch.setattr("jobs.sync.manual.sync_item", sync_item)
    monkeypatch.setattr("jobs.sync.manual.run_analysis", lambda session: None)

    assert claim_manual_sync() is True
    run_claimed_manual_sync()

    assert kinds == ["MANUAL"]


def test_failed_connection_leaves_a_run_pointing_to_the_connection(
    db_session: Session, monkeypatch: MonkeyPatch
) -> None:
    """A falha precisa dizer QUAL conexão falhou sem citar o `item_id`.

    O `sync_run` que o `sync_item` criou some no rollback da transação que
    falhou, então o vínculo é reconsultado por `item_id` — e o texto do erro
    continua redigido, porque o identificador vive na coluna, não na frase.
    """
    item_id = uuid.uuid4()
    connection = _connection(db_session, item_id)

    @contextmanager
    def same_session() -> Iterator[Session]:
        yield db_session

    def sync_item(
        session: Session, client: object, current_item_id: str, *, kind: str = "INCREMENTAL"
    ) -> SyncResult:
        request = httpx.Request("GET", f"https://api.pluggy.ai/items/{current_item_id}/accounts")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("erro na Pluggy", request=request, response=response)

    monkeypatch.setenv("PLUGGY_CLIENT_ID", "client-id")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr("jobs.sync.manual.create_session", same_session)
    monkeypatch.setattr("jobs.sync.manual.PluggyClient", _FakePluggyClient)
    monkeypatch.setattr("jobs.sync.manual.sync_item", sync_item)

    assert claim_manual_sync() is True
    run_claimed_manual_sync()

    failure = db_session.scalar(
        select(SyncRun).where(SyncRun.status == "FAILED", SyncRun.connection_id.is_not(None))
    )
    assert failure is not None
    assert failure.kind == "MANUAL"
    assert failure.connection_id == connection.id
    assert failure.error_message is not None
    assert str(item_id) not in failure.error_message
