import argparse
import datetime as dt
import os
import sys

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from core.locks import sync_lock
from core.models import SyncRun
from core.redaction import redact_identifiers
from jobs.pluggy.client import PluggyClient
from jobs.sync.run import sync_item


def _record_failure(engine: Engine, exc: BaseException) -> None:
    now = dt.datetime.now(dt.UTC)
    with Session(engine) as session:
        session.add(
            SyncRun(
                kind="INCREMENTAL",
                started_at=now,
                finished_at=now,
                status="FAILED",
                error_message=redact_identifiers(str(exc)),
            )
        )
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sincroniza um item (connection) da Pluggy com o Postgres local."
    )
    parser.add_argument("item_id", help="UUID do item na Pluggy")
    parser.add_argument(
        "--kind",
        choices=["FULL", "INCREMENTAL"],
        default="INCREMENTAL",
        help="FULL ignora o cursor incremental e relê os 12 meses; INCREMENTAL usa o cursor.",
    )
    args = parser.parse_args()

    client_id = os.environ["PLUGGY_CLIENT_ID"]
    client_secret = os.environ["PLUGGY_CLIENT_SECRET"]
    database_url = os.environ["DATABASE_URL"]

    engine = create_engine(database_url)
    # O mesmo lock que a API usa: um sync disparado pela tela e o CronJob das
    # 06:00 não podem rodar juntos contra a mesma conexão Pluggy.
    with sync_lock() as acquired:
        if not acquired:
            print("sync ignorado: já existe uma sincronização em andamento")
            return 0
        with Session(engine) as session, PluggyClient(client_id, client_secret) as client:
            try:
                result = sync_item(session, client, args.item_id, kind=args.kind)
                session.commit()
            except Exception as exc:
                session.rollback()
                # O rollback leva junto o sync_run de falha que o sync_item tinha
                # criado — até 2026-08-23 uma falha de CronJob não deixava rastro
                # nenhum, e o histórico da tela mostrava só sucesso. Regravamos
                # numa sessão limpa, senão o rollback apagaria de novo.
                _record_failure(engine, exc)
                raise

    print(
        f"sync_run={result.sync_run_id} contas={result.accounts_synced} "
        f"investimentos={result.investments_synced} "
        f"inseridas={result.tx_inserted} atualizadas={result.tx_updated} "
        f"duplicadas={result.tx_duplicates}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
