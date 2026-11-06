from decimal import Decimal
from typing import Any

from jobs.pluggy.schemas import PluggyAccount
from jobs.sync.mapping import map_account


def _card_json(credit_data: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "id": "22222222-2222-2222-2222-222222222299",
        "itemId": "11111111-1111-1111-1111-111111111111",
        "type": "CREDIT",
        "subtype": "CREDIT_CARD",
        "number": "1029",
        "currencyCode": "BRL",
        "balance": "2803.00",
        "creditData": credit_data,
    }


def _installment_credit(credit_data: dict[str, Any] | None) -> Decimal | None:
    account = PluggyAccount.model_validate(_card_json(credit_data))
    return map_account(account, connection_id=1, connector_id=200).installment_credit_used


def test_installment_credit_is_none_when_the_bank_does_not_report_the_line() -> None:
    assert _installment_credit(None) is None
    assert _installment_credit({"creditLimit": "2793"}) is None
    assert _installment_credit({"disaggregatedCreditLimits": None}) is None
    assert (
        _installment_credit(
            {"disaggregatedCreditLimits": [{"lineName": "SAQUE_CREDITO_BRASIL", "usedAmount": 0}]}
        )
        is None
    )


def test_installment_credit_zero_reported_is_zero_not_none() -> None:
    assert _installment_credit(
        {"disaggregatedCreditLimits": [{"lineName": "CREDITO_PARCELADO", "usedAmount": 0}]}
    ) == Decimal("0")
