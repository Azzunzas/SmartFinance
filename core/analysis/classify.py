import re
from dataclasses import dataclass

CARD_PAYMENT_CATEGORY_NAME = "Pagamento de fatura"

# Regra de domínio 2: pagamento de fatura não é despesa. Contar as duas coisas
# (a compra no cartão E o pagamento da fatura) dobra o gasto.
#
# A categoria da Pluggy sozinha não basta. Medido no banco real em 2026-08-23: o
# PicPay classifica o próprio pagamento de fatura como "Transfers", não como
# "Credit card payment". A rede de segurança seria o detector de transferência
# interna — a saída na carteira casando com a entrada no cartão —, mas ela só
# funciona quando a conta do cartão também tem o registro espelho, e a Pluggy dá
# histórico curto pra cartão (23 e 86 transações contra 490 da carteira). Nos
# meses em que o espelho não existe, o pagamento passava direto e virava despesa:
# **8 transações**, espalhadas por 7 meses.
#
# Casar pela descrição é heurística, e heurística pode dar falso positivo — o
# custo aqui seria esconder uma despesa real. Aceito porque a frase é
# inequívoca: conferidas as 5 descrições distintas que batem no padrão no banco
# real, todas são pagamento de fatura de verdade.
_CARD_PAYMENT_DESCRIPTION_RE = re.compile(r"\bpagamento d[ae] fatura\b")

# `operationType` do Open Finance (Pluggy, desde setembro de 2026). Vem da
# instituição ou é inferido pela Pluggy — no segundo caso, para pagamentos que
# ela mesma gera e que antes chegavam com `null`. É o sinal mais direto dos três,
# mas só existe em transação recente e só em cartão, por isso não substitui os
# outros.
CARD_PAYMENT_OPERATION_TYPE = "PAGAMENTO_FATURA"


@dataclass(frozen=True, slots=True)
class CategoryLookup:
    category_id: int
    category_name: str
    kind: str


def resolve_category(
    pluggy_category: str | None, mapping: dict[str, CategoryLookup]
) -> CategoryLookup | None:
    """`None` quando a Pluggy não mandou categoria, ou quando mandou uma que a
    gente ainda não mapeou — de propósito visível como "sem categoria" em vez
    de cair silenciosamente num "Outros" que esconderia a lacuna."""
    if pluggy_category is None:
        return None
    return mapping.get(pluggy_category)


def is_card_payment(
    category: CategoryLookup | None,
    description_norm: str = "",
    operation_type: str | None = None,
) -> bool:
    """Pagamento de fatura pelo `operationType`, pela categoria da Pluggy **ou**
    pela descrição.

    A via da descrição existe porque a da categoria falha em silêncio quando o
    banco categoriza o pagamento como transferência — ver comentário no topo do
    módulo.
    """
    if operation_type == CARD_PAYMENT_OPERATION_TYPE:
        return True
    if category is not None and category.category_name == CARD_PAYMENT_CATEGORY_NAME:
        return True
    return bool(_CARD_PAYMENT_DESCRIPTION_RE.search(description_norm))
