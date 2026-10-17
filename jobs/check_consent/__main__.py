import os
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobs.check_consent.run import run_check_consent


def main() -> int:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)

    with Session(engine) as session:
        result = run_check_consent(session, now=datetime.now(UTC))

    print(f"conexões_verificadas={result.connections_checked} em_risco={len(result.at_risk)}")
    for health in result.at_risk:
        reasons = []
        if health.consent_expiring:
            reasons.append(f"consentimento expira em {health.consent_expires_at}")
        if health.connection_stale:
            reasons.append(
                f"sem atualização da Pluggy desde {health.last_updated_at} "
                f"(status={health.status})"
            )
        print(f"  ALERTA [{health.connector_name}]: {'; '.join(reasons)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
