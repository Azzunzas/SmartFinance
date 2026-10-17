import datetime as dt


def as_instant(value: dt.date | dt.datetime) -> dt.datetime:
    """`transaction.occurred_at` é NOT NULL desde a migration 0014 — o
    fingerprint passou a depender do horário, não só do dia. Testes que só se
    importam com o dia civil usam meia-noite UTC dele; testes que precisam
    distinguir duas transações no mesmo dia passam o datetime de verdade."""
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    return dt.datetime.combine(value, dt.time(), tzinfo=dt.UTC)
