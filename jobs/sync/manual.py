import datetime as dt
import os
from contextlib import suppress

import httpx

from core.database import create_session
from core.locks import SyncLock, sync_lock_held
from core.models import SyncRun
from core.redaction import redact_identifiers
from core.repository.connections import (
    deactivate_connection_by_item_id,
    list_active_pluggy_item_ids,
    load_connection_id_by_item_id,
)
from jobs.analysis.run import run_analysis
from jobs.pluggy.client import PluggyClient
from jobs.sync.run import sync_item

# Advisory lock do Postgres, não threading.Lock. Até 2026-08-23 era em memória,
# o que valia só dentro de UM processo: o CronJob das 06:00 e um clique em
# "Sincronizar agora" podiam rodar juntos contra a mesma conexão Pluggy, e duas
# réplicas da API idem. Ver core/locks.py.
_manual_sync_lock = SyncLock()


def claim_manual_sync() -> bool:
    """Reserva a execução de sync — contra qualquer processo, não só este."""
    return _manual_sync_lock.acquire()


def manual_sync_running() -> bool:
    """Estado consultável pela UI. Pergunta ao Postgres em vez de olhar o estado
    local, então enxerga também o sync disparado pelo CronJob."""
    return sync_lock_held()


def run_claimed_manual_sync() -> None:
    """Sincroniza conexões ativas e grava um resultado agregado para a UI."""
    manual_run_id: int | None = None
    successful_connections = 0
    failed_connections = 0
    deactivated_connections = 0
    tx_inserted = 0
    tx_updated = 0
    tx_duplicates = 0
    finalized = False

    try:
        manual_run_id = _create_manual_run()
        with create_session() as session:
            item_ids = list_active_pluggy_item_ids(session)

        client_id = os.environ["PLUGGY_CLIENT_ID"]
        client_secret = os.environ["PLUGGY_CLIENT_SECRET"]
        any_success = False
        with PluggyClient(client_id, client_secret) as client:
            for item_id in item_ids:
                with create_session() as session:
                    try:
                        # `kind="MANUAL"` aqui é só rótulo de ORIGEM: quem muda
                        # comportamento é `kind="FULL"` (ignora o cursor), e
                        # qualquer outro valor segue incremental. Sem esse
                        # rótulo, a linha por conexão — a única que carrega
                        # `connection_id` — ficava indistinguível de uma
                        # execução do CronJob, e a tela, que filtra por MANUAL,
                        # só enxergava a agregada, que não tem banco nenhum.
                        result = sync_item(session, client, item_id, kind="MANUAL")
                        session.commit()
                        any_success = True
                        successful_connections += 1
                        tx_inserted += result.tx_inserted
                        tx_updated += result.tx_updated
                        tx_duplicates += result.tx_duplicates
                    except Exception as exc:
                        session.rollback()
                        _record_failure(item_id, str(exc))
                        failed_connections += 1
                        if _is_missing_pluggy_item(exc, item_id):
                            with create_session() as cleanup_session:
                                if deactivate_connection_by_item_id(cleanup_session, item_id):
                                    cleanup_session.commit()
                                    deactivated_connections += 1

        if any_success:
            with create_session() as session:
                run_analysis(session)
                session.commit()

        status = (
            "PARTIAL"
            if successful_connections > 0 and failed_connections > 0
            else "FAILED"
            if failed_connections > 0
            else "SUCCESS"
        )
        _finish_manual_run(
            manual_run_id,
            status=status,
            tx_inserted=tx_inserted,
            tx_updated=tx_updated,
            tx_duplicates=tx_duplicates,
            error_message=_manual_run_message(
                total=len(item_ids),
                failed=failed_connections,
                deactivated=deactivated_connections,
            ),
        )
        finalized = True
    except Exception as exc:
        if manual_run_id is not None and not finalized:
            status = "PARTIAL" if successful_connections > 0 else "FAILED"
            with suppress(Exception):
                _finish_manual_run(
                    manual_run_id,
                    status=status,
                    tx_inserted=tx_inserted,
                    tx_updated=tx_updated,
                    tx_duplicates=tx_duplicates,
                    error_message=redact_identifiers(f"Falha ao finalizar a sincronização: {exc}"),
                )
        raise
    finally:
        _manual_sync_lock.release()


def _create_manual_run() -> int:
    with create_session() as session:
        run = SyncRun(kind="MANUAL", status="RUNNING")
        session.add(run)
        session.commit()
        return run.id


def _finish_manual_run(
    run_id: int,
    *,
    status: str,
    tx_inserted: int,
    tx_updated: int,
    tx_duplicates: int,
    error_message: str | None,
) -> None:
    with create_session() as session:
        run = session.get(SyncRun, run_id)
        if run is None:
            raise RuntimeError(f"sync manual {run_id} não encontrado")
        run.finished_at = dt.datetime.now(dt.UTC)
        run.status = status
        run.tx_inserted = tx_inserted
        run.tx_updated = tx_updated
        run.tx_duplicates = tx_duplicates
        run.error_message = error_message
        session.commit()


def _is_missing_pluggy_item(exc: Exception, item_id: str) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response.status_code == 404
        and exc.request.url.path.rstrip("/") == f"/items/{item_id}"
    )


def _manual_run_message(*, total: int, failed: int, deactivated: int) -> str | None:
    if total == 0:
        return "Nenhuma conexão ativa para sincronizar."
    if failed == 0:
        return None

    failed_verb = "falhou" if failed == 1 else "falharam"
    message = f"{failed} de {total} conexões {failed_verb}."
    if deactivated > 0:
        noun = "conexão indisponível" if deactivated == 1 else "conexões indisponíveis"
        verb = "foi desativada" if deactivated == 1 else "foram desativadas"
        message += f" {deactivated} {noun} na Pluggy {verb}."
    return message


def _record_failure(item_id: str, message: str) -> None:
    """Rastro da conexão que falhou, dizendo QUAL conexão foi.

    Até 2026-08-24 esta linha era gravada como `kind="INCREMENTAL"` e sem
    `connection_id`: anônima e indistinguível de uma execução do CronJob. A
    conexão é reconsultada por `item_id` porque o `sync_run` que o `sync_item`
    tinha criado já foi desfeito pelo rollback da transação que falhou.
    """
    now = dt.datetime.now(dt.UTC)
    with create_session() as session:
        session.add(
            SyncRun(
                kind="MANUAL",
                started_at=now,
                finished_at=now,
                status="FAILED",
                connection_id=load_connection_id_by_item_id(session, item_id),
                error_message=redact_identifiers(message),
            )
        )
        session.commit()
