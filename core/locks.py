"""Exclusão mútua entre processos, via advisory lock do Postgres.

Por que não um `threading.Lock`: ele vale dentro de UM processo Python. A API e
o CronJob de sync são processos diferentes — e a própria API pode ter mais de um
worker ou mais de uma réplica. Com lock em memória, o CronJob das 06:00 e um
clique em "Sincronizar agora" rodavam ao mesmo tempo contra a mesma conexão
Pluggy, sem nada impedir.

O advisory lock resolve porque o árbitro passa a ser o banco, que os dois já
compartilham — sem infraestrutura nova (docs/regras-do-projeto.md §4 veta fila
ou serviço extra sem gargalo medido).

Duas propriedades verificadas contra o Postgres real antes de escrever isto:

1. **Fechar a `Connection` do SQLAlchemy NÃO solta o lock.** A conexão volta pro
   pool viva, e o Postgres continua enxergando a sessão como dona. Por isso o
   `finally` abaixo faz `pg_advisory_unlock` explícito — não é higiene, é o que
   evita um lock preso pra sempre.
2. **Se o processo morrer, o lock é solto.** A conexão TCP cai junto e o
   Postgres libera. Ou seja: não existe o problema clássico de lock órfão depois
   de um crash.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa
from sqlalchemy import Connection

from core.database import create_connection

# Chave arbitrária, mas fixa e única no banco: quem mudar isto solta a exclusão
# mútua sem erro nenhum aparecer.
SYNC_LOCK_KEY = 4_209_130_711

# pg_locks guarda a chave bigint partida em dois int32. Consultar essas colunas é
# o único jeito de PERGUNTAR se o lock está preso sem tentar pegá-lo — e
# `pg_try_advisory_lock` não serve pra isso, porque ele adquire quando está livre.
_CLASSID = SYNC_LOCK_KEY >> 32
_OBJID = SYNC_LOCK_KEY & 0xFFFFFFFF

_IS_HELD_SQL = sa.text(
    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
    "AND classid = :classid AND objid = :objid)"
)


class SyncLock:
    """Posse explícita do lock, para quando ele precisa atravessar escopos.

    A API precisa disso: `POST /api/sync/run` pega o lock e responde 202 na
    hora, e quem solta é a `BackgroundTask` que roda depois. Um `with` não
    alcança os dois lados.

    O `threading.Lock` interno não substitui o advisory lock — ele só torna
    `acquire`/`release` atômicos entre threads DESTE processo, protegendo o
    atributo `_connection`. A exclusão entre processos continua sendo do
    Postgres.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._connection: Connection | None = None

    def acquire(self) -> bool:
        with self._guard:
            if self._connection is not None:
                return False
            connection = create_connection()
            try:
                acquired = bool(
                    connection.execute(
                        sa.text("SELECT pg_try_advisory_lock(:key)"), {"key": SYNC_LOCK_KEY}
                    ).scalar_one()
                )
            except Exception:
                connection.close()
                raise
            if not acquired:
                connection.close()
                return False
            self._connection = connection
            return True

    def release(self) -> None:
        with self._guard:
            connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            connection.execute(
                sa.text("SELECT pg_advisory_unlock(:key)"), {"key": SYNC_LOCK_KEY}
            )
        finally:
            # Fechar sozinho NÃO soltaria o lock (a conexão volta viva pro pool)
            # — por isso o unlock acima vem antes, sempre.
            connection.close()


@contextmanager
def sync_lock() -> Iterator[bool]:
    """Escopo simples, para quem começa e termina no mesmo lugar (o CronJob).

    Devolve True se pegou. Se devolveu False, quem chamou NÃO pode sincronizar —
    outro processo está no meio de um sync.
    """
    lock = SyncLock()
    try:
        yield lock.acquire()
    finally:
        lock.release()


def sync_lock_held() -> bool:
    """Só pergunta, não adquire — é o que o `GET /api/sync/status` precisa."""
    with create_connection() as connection:
        return bool(
            connection.execute(_IS_HELD_SQL, {"classid": _CLASSID, "objid": _OBJID}).scalar_one()
        )
