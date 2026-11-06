import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.ingestion.normalize import compute_account_fingerprint
from core.models import Account, BalanceSnapshot, Connection
from core.repository.accounts import AccountUpsert, upsert_account


def _connection(db_session: Session, connector_id: int = 601) -> int:
    connection = Connection(
        pluggy_item_id=uuid.uuid4(),
        connector_id=connector_id,
        connector_name="MeuPluggy",
        status="UPDATED",
        raw={},
    )
    db_session.add(connection)
    db_session.flush()
    return connection.id


def _card(connection_id: int, *, balance: Decimal, number_masked: str = "1029") -> AccountUpsert:
    """O mesmo cartão físico, do jeito que a Pluggy o descreve."""
    return AccountUpsert(
        connection_id=connection_id,
        pluggy_account_id=uuid.uuid4(),
        fingerprint=compute_account_fingerprint(601, "CREDIT_CARD", number_masked),
        type="CREDIT",
        subtype="CREDIT_CARD",
        name="CARTAO DE TESTE",
        number_masked=number_masked,
        currency_code="BRL",
        balance=balance,
        credit_limit=Decimal("5000.00"),
        available_credit_limit=Decimal("3000.00"),
        brand="MASTERCARD",
        balance_due_date=None,
        balance_close_date=None,
        minimum_payment=None,
        installment_credit_used=None,
        raw={},
    )


def test_reconnecting_does_not_create_a_second_account(db_session: Session) -> None:
    """Reconexão gera `accountId` novo pra MESMA conta física.

    Até 2026-08-24 o upsert casava por `pluggy_account_id`, então isso inseria
    uma linha nova e a antiga continuava com `is_own`/`include_in_analysis`
    ligados — e `load_overview` filtra só por esses dois, sem olhar se a
    conexão ainda está ativa. O saldo do cartão passaria a ser contado duas
    vezes no patrimônio.
    """
    primeira_conexao = _connection(db_session)
    account_id = upsert_account(db_session, _card(primeira_conexao, balance=Decimal("100.00")))

    # O usuário reconecta: item novo, accountId novo, mesmo cartão.
    segunda_conexao = _connection(db_session)
    depois = _card(segunda_conexao, balance=Decimal("250.00"))
    account_id_depois = upsert_account(db_session, depois)

    assert account_id_depois == account_id, "a reconexão criou uma segunda linha de conta"

    contas = db_session.scalar(
        select(func.count())
        .select_from(Account)
        .where(Account.fingerprint == depois.fingerprint)
    )
    assert contas == 1

    conta = db_session.get(Account, account_id)
    assert conta is not None
    assert conta.pluggy_account_id == depois.pluggy_account_id, "não adotou o id novo da Pluggy"
    assert conta.connection_id == segunda_conexao, "ficou preso na conexão antiga"
    assert conta.balance == Decimal("250.00")


def test_reconnecting_keeps_the_balance_history(db_session: Session) -> None:
    """O histórico mora no `account_id` interno; adotar o id novo tem que preservá-lo.

    É o que separa "reconectei" de "perdi a série": `balance_snapshot` é a única
    fonte de patrimônio histórico, e a API não devolve saldo passado. Com uma
    linha de conta nova, os snapshots antigos ficariam órfãos numa conta que
    ninguém mais atualiza — e o forward-fill do `/metrics/networth` continuaria
    somando aquele saldo congelado para sempre.

    O teste faz uma captura só de propósito: `func.now()` no Postgres é o
    instante de início da TRANSAÇÃO, então duas capturas na mesma transação
    colidiriam na PK `(account_id, captured_at)` e a segunda cairia no
    `DO NOTHING`. Na prática cada sync roda na sua própria transação, então isso
    não aparece — mas invalidaria a asserção aqui.
    """
    antes = _card(_connection(db_session), balance=Decimal("10.00"))
    account_id = upsert_account(db_session, antes)
    upsert_account(db_session, _card(_connection(db_session), balance=Decimal("20.00")))

    snapshots = db_session.scalars(
        select(BalanceSnapshot.balance).where(BalanceSnapshot.account_id == account_id)
    ).all()
    assert list(snapshots) == [Decimal("10.00")], "o snapshot anterior à reconexão se perdeu"


@pytest.mark.parametrize("campo", ["is_own", "include_in_analysis"])
def test_sync_does_not_undo_the_users_decision(db_session: Session, campo: str) -> None:
    """`is_own` e `include_in_analysis` são escolha do usuário, não dado da Pluggy.

    Se entrassem em `_UPDATABLE_FIELDS`, todo sync desfaria a decisão de tirar
    uma conta da análise — em silêncio, e os totais mudariam sozinhos.
    """
    conexao = _connection(db_session)
    account_id = upsert_account(db_session, _card(conexao, balance=Decimal("10.00")))

    conta = db_session.get(Account, account_id)
    assert conta is not None
    setattr(conta, campo, False)
    db_session.flush()

    upsert_account(db_session, _card(conexao, balance=Decimal("30.00")))

    db_session.refresh(conta)
    assert getattr(conta, campo) is False
    assert conta.balance == Decimal("30.00"), "o sync deveria continuar atualizando o saldo"
