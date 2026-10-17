"""O lock de sync precisa valer ENTRE processos, não dentro de um.

Cada `SyncLock` abre a própria conexão com o Postgres, então duas instâncias
reproduzem fielmente dois processos disputando — que é o caso real: o CronJob
das 06:00 e a API respondendo a um clique em "Sincronizar agora".
"""

from core.locks import SyncLock, sync_lock, sync_lock_held


def test_second_holder_cannot_acquire_while_first_holds() -> None:
    primeiro, segundo = SyncLock(), SyncLock()
    assert primeiro.acquire() is True
    try:
        assert segundo.acquire() is False  # <- era True quando o lock era em memória
        assert sync_lock_held() is True
    finally:
        primeiro.release()

    # solto o lock, o outro consegue
    assert segundo.acquire() is True
    segundo.release()
    assert sync_lock_held() is False


def test_release_is_explicit_because_closing_does_not_free_it() -> None:
    """Fechar a Connection do SQLAlchemy devolve ela viva pro pool, e o Postgres
    continua enxergando a sessão como dona do lock. Sem `pg_advisory_unlock`
    explícito, o lock ficaria preso até o processo morrer."""
    lock = SyncLock()
    assert lock.acquire() is True
    lock.release()
    assert sync_lock_held() is False


def test_release_without_acquire_is_harmless() -> None:
    SyncLock().release()
    assert sync_lock_held() is False


def test_context_manager_frees_on_exception() -> None:
    class Boom(Exception):
        pass

    try:
        with sync_lock() as acquired:
            assert acquired is True
            raise Boom
    except Boom:
        pass
    assert sync_lock_held() is False


def test_context_manager_reports_false_when_already_held() -> None:
    outro = SyncLock()
    assert outro.acquire() is True
    try:
        with sync_lock() as acquired:
            assert acquired is False
    finally:
        outro.release()
