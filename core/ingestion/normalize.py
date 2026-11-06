import calendar
import hashlib
import re
import unicodedata
from datetime import UTC, date, datetime
from decimal import Decimal

from core.models.transaction import Direction

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")

_CENTS = Decimal("0.01")


def normalize_description(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = without_accents.lower()
    without_punctuation = _NON_ALNUM_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_punctuation).strip()


def mask_account_number(number: str | None) -> str | None:
    if number is None:
        return None
    visible = number[-4:]
    hidden = "•" * max(len(number) - 4, 0)
    return f"{hidden}{visible}"


def compute_account_fingerprint(
    connector_id: int, subtype: str | None, number_masked: str | None
) -> str:
    raw = f"{connector_id}|{subtype or ''}|{number_masked or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def resolve_direction(account_type: str, amount: Decimal) -> Direction:
    """§4.1 do arquitetura doc: conta CREDIT inverte a leitura humana do sinal —
    valor positivo é compra (aumenta a fatura), negativo é pagamento/estorno.
    Conta BANK segue o sinal cru da Pluggy: negativo = saída, positivo = entrada."""
    is_negative = amount < 0
    is_credit_account = account_type == "CREDIT"
    return Direction.OUT if is_negative != is_credit_account else Direction.IN


def resolve_card_credit(account_type: str, direction: Direction) -> bool:
    """Crédito lançado na conta do cartão: pagamento de fatura, estorno,
    "pula compra", cashback. Resolvido aqui, uma vez, pelo mesmo motivo de
    `resolve_direction` (regra de domínio 9): a view de fluxo de caixa precisa
    dele e não pode decidir por `account.type`.

    O que sobra depois das exclusões de pagamento de fatura e transferência
    interna abate gasto, nunca é receita (regra 11, migration 0019)."""
    return account_type == "CREDIT" and direction is Direction.IN


def _subtract_months(reference: date, months: int) -> date:
    month_index = reference.month - 1 - months
    year = reference.year + month_index // 12
    month = month_index % 12 + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def resolve_accrual_date(
    posted_date: date, installment_number: int | None, installment_total: int | None
) -> date:
    """Regra de domínio 1 (regime de competência): a Pluggy só garante que
    `date` é a data da compra pra parcela 1. Da parcela 2 em diante, `date` vira
    a data de postagem na fatura — varia por banco, e a Pluggy não expõe a data
    de compra original pras parcelas seguintes. Decisão consciente (não é bug):
    inferimos subtraindo (N-1) meses de `date`. Funciona bem em ciclo mensal
    regular; pode errar o mês perto de virada de fatura em banco com ciclo
    irregular (fechamento e vencimento distantes). Ver conversa que aprovou isso."""
    if installment_number is None or installment_number <= 1:
        return posted_date
    return _subtract_months(posted_date, installment_number - 1)


def compute_transaction_fingerprint(
    account_fingerprint: str,
    occurred_at: datetime,
    amount_abs: Decimal,
    direction: Direction,
    description_norm: str,
) -> str:
    """Identidade de negócio de uma transação, usada pra reconhecer a MESMA
    transação quando a Pluggy manda um id novo (reconexão, ou registro recriado
    quando a transação liquida).

    Usa o **instante**, não o dia. Até a migration 0014 usava só a data, e isso
    engolia transações reais: duas idênticas no mesmo dia (dois PIX recebidos de
    R$7, mesma descrição genérica) colidiam e a segunda era descartada. Medido
    contra a API em 2026-08-23: **6 transações** tinham sido perdidas assim,
    todas receita — o que subestimava a entrada de dinheiro.

    Descartadas antes de chegar aqui: `balance` (a Pluggy manda None nas 858
    transações checadas) e `providerId` (também None). O horário resolveu 6 de 6
    colisões reais, e nenhuma transação vem à meia-noite — o horário é
    informação de verdade em conta BANK e CREDIT.

    Risco assumido: se a Pluggy mudar o horário de uma transação entre PENDING e
    POSTED, o fingerprint muda junto e a linha PENDING vira órfã em vez de ser
    atualizada. Não deu pra observar isso (nenhuma PENDING liquidou durante a
    investigação). A perda de 6 transações é medida; esse risco é hipotético.
    """
    quantized = amount_abs.quantize(_CENTS)
    instant = occurred_at.astimezone(UTC).isoformat()
    raw = (
        f"{account_fingerprint}|{instant}|{quantized}|"
        f"{direction.value}|{description_norm}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()
