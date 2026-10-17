from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from core.models.transaction import Direction

DEFAULT_WINDOW_DAYS = 2

#: Tipo de conta em que uma saída é compra num comerciante, não movimentação
#: entre contas suas. Ver `is_transfer_eligible`.
_PURCHASE_ONLY_OUT_TYPE = "CREDIT"


def is_transfer_eligible(*, is_own_account: bool, account_type: str, direction: Direction) -> bool:
    """Quem pode entrar no pool de candidatos a transferência interna.

    Duas condições, e a segunda é correção de bug de 2026-08-24:

    1. **Conta própria** (regra de domínio 3). Transferência pra terceiro é
       despesa de verdade.
    2. **Saída num cartão de crédito nunca entra.** Numa conta `CREDIT`, `OUT`
       é compra — o dinheiro vai pro comerciante, não pra outra conta sua. O
       único movimento entre contas próprias que envolve cartão é o pagamento
       da fatura, que é `IN` no cartão e já tem tratamento próprio
       (`is_card_payment`).

    Sem a condição 2, qualquer compra no cartão virava candidata a casar com um
    PIX recebido de mesmo valor em ±2 dias. Casos reais medidos no banco em
    2026-08-24: PIX recebidos casaram com compras de mesmo valor no cartão feitas
    dois dias depois. Foram três pares falsos, e o erro conta **dobrado**, porque
    marcar o par exclui a receita *e* a despesa das somas.

    O bug estava dormente desde sempre e só apareceu quando uma reconexão do
    PicPay recuperou 71 compras de cartão que a Pluggy não vinha entregando:
    de repente havia dezenas de candidatos a par acidental. Detector frouxo com
    pouco dado parece detector certo.

    **Caso conhecido que este filtro sacrifica:** saque na função crédito
    (dinheiro do limite caindo na conta) é `OUT` no cartão + `IN` no banco, e
    seria transferência interna legítima. Decisão de 2026-08-24: esse uso não
    acontece neste projeto, e o falso positivo medido vale mais que o caso
    hipotético. Se um dia acontecer, a saída aparece como despesa e a entrada como
    receita — visível e corrigível à mão, que é melhor do que sumir em silêncio.
    """
    if not is_own_account:
        return False
    return not (account_type == _PURCHASE_ONLY_OUT_TYPE and direction is Direction.OUT)


@dataclass(frozen=True, slots=True)
class TransferCandidate:
    """Pré-requisito de quem chama: só passe transações de contas com
    `is_own = true`. Essa função não sabe nada sobre `account`, de propósito —
    filtrar por conta própria é decisão de quem monta a lista, não do algoritmo."""

    transaction_id: int
    account_id: int
    date: date
    amount_abs: Decimal
    direction: Direction


@dataclass(frozen=True, slots=True)
class TransferMatch:
    out_transaction_id: int
    in_transaction_id: int


def match_internal_transfers(
    candidates: Sequence[TransferCandidate], *, window_days: int = DEFAULT_WINDOW_DAYS
) -> list[TransferMatch]:
    """§4.3 do arquitetura doc: casa um OUT numa conta própria com um IN de
    mesmo valor em outra conta própria, dentro de ±window_days.

    Determinístico de propósito (ordena por data e id antes de casar, desempata
    pelo par mais próximo em dias e depois por id) — rodar duas vezes com o
    mesmo conjunto de transações sempre produz o mesmo resultado. Cada
    transação entra em no máximo um par: uma vez usada, sai do pool.
    """
    outs = sorted(
        (c for c in candidates if c.direction is Direction.OUT),
        key=lambda c: (c.date, c.transaction_id),
    )
    ins = sorted(
        (c for c in candidates if c.direction is Direction.IN),
        key=lambda c: (c.date, c.transaction_id),
    )

    consumed_in_ids: set[int] = set()
    matches: list[TransferMatch] = []

    for out in outs:
        best: TransferCandidate | None = None
        best_gap = window_days + 1

        for candidate in ins:
            if candidate.transaction_id in consumed_in_ids:
                continue
            if candidate.account_id == out.account_id:
                continue
            if candidate.amount_abs != out.amount_abs:
                continue

            gap = abs((candidate.date - out.date).days)
            if gap > window_days:
                continue

            if (
                best is None
                or gap < best_gap
                or (gap == best_gap and candidate.transaction_id < best.transaction_id)
            ):
                best = candidate
                best_gap = gap

        if best is not None:
            matches.append(
                TransferMatch(
                    out_transaction_id=out.transaction_id, in_transaction_id=best.transaction_id
                )
            )
            consumed_in_ids.add(best.transaction_id)

    return matches
