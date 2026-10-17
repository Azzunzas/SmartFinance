from core.analysis.classify import CategoryLookup, is_card_payment, resolve_category

_MAPPING = {
    "Eating out": CategoryLookup(category_id=1, category_name="Alimentação", kind="EXPENSE"),
    "Credit card payment": CategoryLookup(
        category_id=2, category_name="Pagamento de fatura", kind="TRANSFER"
    ),
}


def test_resolve_category_known_pluggy_category() -> None:
    result = resolve_category("Eating out", _MAPPING)
    assert result is not None
    assert result.category_name == "Alimentação"


def test_resolve_category_unknown_pluggy_category_is_none() -> None:
    assert resolve_category("Something new the Pluggy invented", _MAPPING) is None


def test_resolve_category_none_input_is_none() -> None:
    assert resolve_category(None, _MAPPING) is None


def test_is_card_payment_true_for_card_payment_category() -> None:
    category = resolve_category("Credit card payment", _MAPPING)
    assert is_card_payment(category) is True


def test_is_card_payment_false_for_other_category() -> None:
    category = resolve_category("Eating out", _MAPPING)
    assert is_card_payment(category) is False


def test_is_card_payment_false_when_category_is_none() -> None:
    assert is_card_payment(None) is False


def test_card_payment_detected_by_description_when_category_says_transfer() -> None:
    """Regressão de 2026-08-23. O PicPay classifica o próprio pagamento de fatura
    como "Transfers". Sem a via da descrição, 8 pagamentos viravam despesa comum,
    gasto que nunca existiu, violando a regra de domínio 2."""
    transferencia = CategoryLookup(category_id=9, category_name="Transferências", kind="EXPENSE")
    assert is_card_payment(transferencia, "pagamento de fatura picpay card") is True
    assert is_card_payment(None, "pagamento da fatura picpay via raspa conta") is True
    assert is_card_payment(None, "pagamento de fatura pelo picpay") is True


def test_card_payment_by_description_does_not_swallow_ordinary_spending() -> None:
    """O custo de um falso positivo aqui é esconder uma despesa real, então o
    padrão tem que ser específico: exige a frase inteira."""
    assert is_card_payment(None, "pagamento boleto energia") is False
    assert is_card_payment(None, "fatura de agua") is False
    assert is_card_payment(None, "mercado central") is False
    assert is_card_payment(None, "") is False
