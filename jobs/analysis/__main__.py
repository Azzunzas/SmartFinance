import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobs.analysis.run import run_analysis


def main() -> int:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)

    with Session(engine) as session:
        try:
            result = run_analysis(session)
            session.commit()
        except Exception:
            session.rollback()
            raise

    print(
        f"transações={result.transactions_processed} "
        f"classificadas={result.classified} "
        f"overrides_manuais={result.manual_overrides} "
        f"pares_transferencia={result.internal_transfer_pairs} "
        f"candidatos_recorrencia={result.recurrence_candidates} "
        f"matches_orcamento={result.planned_item_matches}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
