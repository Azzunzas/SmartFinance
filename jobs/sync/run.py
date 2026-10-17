import datetime as dt
from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from core.models import SyncCursor, SyncRun
from core.redaction import redact_identifiers
from core.repository.accounts import upsert_account
from core.repository.connections import upsert_connection
from core.repository.investments import capture_investment_snapshot, upsert_investment
from core.repository.transactions import upsert_transaction
from jobs.pluggy.client import PluggyClient
from jobs.sync.mapping import map_account, map_connection, map_investment, map_transaction

# Toda execução relê as transações dos últimos N dias por `dateFrom`, além do
# incremental por `createdAtFrom`. Motivo (verificado contra a API em
# 2026-08-23): `createdAtFrom` filtra estritamente por quando a Pluggy criou o
# registro, então uma transação criada antes do cursor nunca volta — e como a
# Pluggy nunca atualiza registro no lugar, o incremental sozinho não entrega
# mudança de status nenhuma. 45 dias cobre um ciclo de fatura inteiro com folga,
# que é onde PENDING demora mais pra liquidar.
REFETCH_WINDOW_DAYS = 45


@dataclass(frozen=True, slots=True)
class SyncResult:
    sync_run_id: int
    accounts_synced: int
    tx_inserted: int
    tx_updated: int
    tx_duplicates: int
    investments_synced: int


def sync_item(
    session: Session, client: PluggyClient, item_id: str, *, kind: str = "INCREMENTAL"
) -> SyncResult:
    """Pipeline completo da Fase 1 pra um item: fetch (Pluggy) -> normalize
    (core/ingestion) -> upsert (core/repository). Não dá commit — quem chama
    controla a fronteira da transação (inclusive se um FAILED entra ou não no
    banco: hoje é tudo ou nada, um sync_run de falha some junto com o rollback;
    conhecido, aceitável pra um usuário só)."""
    started_at = dt.datetime.now(dt.UTC)
    sync_run = SyncRun(kind=kind, status="RUNNING")
    session.add(sync_run)
    session.flush()

    accounts_synced = investments_synced = 0
    tx_inserted = tx_updated = tx_duplicates = 0

    try:
        pluggy_item = client.get_item(item_id)
        connection_id = upsert_connection(session, map_connection(pluggy_item))
        sync_run.connection_id = connection_id

        for pluggy_investment in client.list_investments(item_id):
            investment = map_investment(pluggy_investment, connection_id=connection_id)
            investment_id = upsert_investment(session, investment)
            capture_investment_snapshot(session, investment_id, pluggy_investment.balance)
            investments_synced += 1

        for pluggy_account in client.list_accounts(item_id):
            account = map_account(
                pluggy_account,
                connection_id=connection_id,
                connector_id=pluggy_item.connector.id,
            )
            account_id = upsert_account(session, account)
            accounts_synced += 1

            # `kind="FULL"` ignora o cursor de propósito. Até 2026-08-23 ele era só
            # gravado no `sync_run` e não mudava nada — o cursor era lido sempre, e
            # um "FULL" se comportava igual a um incremental. Isso ficou visível ao
            # tentar recuperar transações antigas: só voltaram as que caíam na
            # janela de releitura, porque um full de verdade nunca acontecia.
            created_at_from = None if kind == "FULL" else _read_cursor(session, account_id)
            refetch_from = started_at.date() - dt.timedelta(days=REFETCH_WINDOW_DAYS)

            # Duas passadas. A primeira é o incremental barato (só o que a Pluggy
            # criou desde o último sync). A segunda relê a janela recente por data
            # da transação, que é o único jeito de uma mudança de status chegar
            # até aqui. Elas se sobrepõem, e tudo bem: o upsert é idempotente —
            # o que a segunda passada reencontra vira "updated" ou "duplicate",
            # nunca linha nova.
            passes = [
                client.iter_transactions(pluggy_account.id, created_at_from=created_at_from)
            ]
            if created_at_from is not None:
                # Só faz sentido no incremental: sem cursor, a passada acima já
                # traz os 12 meses inteiros e a releitura seria trabalho dobrado.
                passes.append(
                    client.iter_transactions(pluggy_account.id, date_from=refetch_from)
                )
            for pluggy_transactions in passes:
                for pluggy_tx in pluggy_transactions:
                    outcome = upsert_transaction(
                        session,
                        map_transaction(
                            pluggy_tx,
                            account_id=account_id,
                            account_type=account.type,
                            account_fingerprint=account.fingerprint,
                        ),
                    )
                    if outcome == "inserted":
                        tx_inserted += 1
                    elif outcome == "updated":
                        tx_updated += 1
                    else:
                        tx_duplicates += 1

            _write_cursor(session, account_id, started_at)

        sync_run.status = "SUCCESS"
    except Exception as exc:
        sync_run.status = "FAILED"
        # Redigido: a exceção da httpx carrega a URL com o item_id dentro.
        sync_run.error_message = redact_identifiers(str(exc))
        raise
    finally:
        sync_run.finished_at = dt.datetime.now(dt.UTC)
        sync_run.tx_inserted = tx_inserted
        sync_run.tx_updated = tx_updated
        sync_run.tx_duplicates = tx_duplicates
        session.flush()

    return SyncResult(
        sync_run_id=sync_run.id,
        accounts_synced=accounts_synced,
        tx_inserted=tx_inserted,
        tx_updated=tx_updated,
        tx_duplicates=tx_duplicates,
        investments_synced=investments_synced,
    )


def _read_cursor(session: Session, account_id: int) -> dt.datetime | None:
    cursor_row = session.get(SyncCursor, account_id)
    if cursor_row is None or cursor_row.cursor is None:
        return None
    return dt.datetime.fromisoformat(cursor_row.cursor)


def _write_cursor(session: Session, account_id: int, synced_at: dt.datetime) -> None:
    """Reaproveita a coluna `sync_cursor.cursor` (TEXT) pra guardar um timestamp
    ISO, não o token de paginação da Pluggy — o `after` só serve pra andar
    dentro de uma busca, não pra retomar no dia seguinte. Esse timestamp vira o
    `createdAtFrom` do próximo sync incremental dessa conta."""
    stmt = (
        pg_insert(SyncCursor)
        .values(account_id=account_id, cursor=synced_at.isoformat())
        .on_conflict_do_update(
            index_elements=["account_id"],
            set_={"cursor": synced_at.isoformat(), "updated_at": dt.datetime.now(dt.UTC)},
        )
    )
    session.execute(stmt)
