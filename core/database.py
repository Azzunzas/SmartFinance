import os

from sqlalchemy import Connection, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = create_engine(os.environ["DATABASE_URL"])
_SessionLocal = sessionmaker(bind=_engine)


def create_session() -> Session:
    """Cria uma sessão para requests HTTP ou jobs executados no mesmo processo."""
    return _SessionLocal()


def create_connection() -> Connection:
    """Conexão crua em AUTOCOMMIT, fora do ciclo de sessão da aplicação.

    Existe pro advisory lock de `core/locks.py`: um lock de sessão do Postgres
    vive enquanto a CONEXÃO viver, então ele precisa de uma conexão própria,
    que não seja aberta e fechada a cada transação do sync. AUTOCOMMIT porque
    segurar uma transação aberta por toda a duração de um sync deixaria o
    Postgres com um `idle in transaction` de minutos à toa.
    """
    return _engine.connect().execution_options(isolation_level="AUTOCOMMIT")
