import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import sqlalchemy as sa
from sqlalchemy import Connection, create_engine
from sqlalchemy.orm import Session

_ROOT = Path(__file__).resolve().parent.parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file(_ROOT / ".env")


def _resolve_test_database_url() -> str:
    """A suíte NUNCA roda contra o banco real.

    Antes de 2026-08-23 ela usava a `DATABASE_URL` de produção direto. Cada
    teste rodava em transação revertida, então na prática não sujava nada — mas
    a corretude da suíte passou a depender do *conteúdo* de um banco vivo com
    dinheiro real dentro, e testes precisavam de truques (períodos em 2030 "que
    garantidamente não existem em produção") pra não colidir com dado seu.

    Ordem de resolução: `DATABASE_URL_TEST` se você definir; senão deriva da
    `DATABASE_URL` acrescentando `_test` ao nome do banco. A checagem final é
    uma trava, não uma formalidade: se as duas URLs coincidirem, a suíte se
    recusa a rodar em vez de escrever no seu extrato.
    """
    explicit = os.environ.get("DATABASE_URL_TEST")
    if explicit:
        test_url = explicit
    else:
        parsed = urlparse(os.environ["DATABASE_URL"])
        test_url = urlunparse(parsed._replace(path=f"{parsed.path}_test"))

    if test_url == os.environ.get("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL_TEST aponta pro mesmo banco da DATABASE_URL. "
            "A suíte apaga e recria o banco de teste a cada execução — "
            "rodar assim destruiria seus dados reais."
        )
    return test_url


TEST_DATABASE_URL = _resolve_test_database_url()

# A partir daqui o processo de teste inteiro enxerga SÓ o banco de teste.
# Não é redundante com as fixtures: `core/database.py` cria a engine na
# importação do módulo, então qualquer código que use `create_session()` ou
# `create_connection()` — o advisory lock de core/locks.py, por exemplo —
# abriria conexão com a URL que estivesse no ambiente naquele instante. Sem esta
# linha, um teste desses escreveria no banco real sem passar por fixture nenhuma.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def _recreate_test_database() -> None:
    """DROP + CREATE a cada execução, depois `alembic upgrade head`.

    Recriar (em vez de reaproveitar) é o que garante que a suíte passe contra um
    banco vazio de verdade — que é exatamente a garantia que faltava antes.
    Também exercita a cadeia inteira de migrations toda vez, de graça: uma
    migration quebrada aparece no `pytest`, não só quando você for aplicar em
    produção.
    """
    parsed = urlparse(TEST_DATABASE_URL)
    database_name = parsed.path.lstrip("/")
    admin_url = urlunparse(parsed._replace(path="/postgres"))

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        # pg_terminate_backend: uma conexão pendurada de uma execução anterior
        # (pytest interrompido no meio) faria o DROP travar esperando por ela.
        connection.execute(
            sa.text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": database_name},
        )
        connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        connection.execute(sa.text(f'CREATE DATABASE "{database_name}"'))
    admin_engine.dispose()

    from alembic.config import Config

    from alembic import command

    # alembic/env.py lê a URL de os.environ["DATABASE_URL"], então apontar o
    # upgrade pro banco de teste é trocar a variável durante a chamada.
    previous = os.environ["DATABASE_URL"]
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    try:
        config = Config(str(_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(_ROOT / "alembic"))
        command.upgrade(config, "head")
    finally:
        os.environ["DATABASE_URL"] = previous


@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    _recreate_test_database()


@pytest.fixture(scope="session")
def db_connection(test_database: None) -> Iterator[Connection]:
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        yield connection
    engine.dispose()


@pytest.fixture
def db_session(db_connection: Connection) -> Iterator[Session]:
    """Cada teste roda dentro de uma transação que é sempre desfeita no final —
    testes não deixam sujeira, mesmo usando savepoints internamente (como o
    upsert_transaction faz pra isolar o conflito de fingerprint)."""
    outer_transaction = db_connection.begin()
    session = Session(bind=db_connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    outer_transaction.rollback()
