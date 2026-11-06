from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Estes schemas espelham o JSON cru da Pluggy (camelCase) — são a "camada bruta".
# Normalização (direction/amount_abs, fingerprint, mapeamento pra category própria)
# acontece depois, no sync job. Nenhum enum de core/models é reaproveitado aqui de
# propósito: se a Pluggy mudar um valor de string amanhã, isso não pode vazar silenciosamente
# pro nosso domínio.
#
# extra="allow": sem isso, todo campo que a Pluggy manda e que a gente não
# declarou aqui é descartado silenciosamente pelo Pydantic antes de virar
# `raw` no banco (mapping.py grava `model_dump()` do objeto já validado, não
# o JSON cru da resposta HTTP) — achado real: os campos brand/balanceDueDate/
# balanceCloseDate/minimumPayment de creditData estavam sendo perdidos assim,
# nunca sobreviveram a nenhum sync já rodado.


class PluggyModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")


class PluggyConnector(PluggyModel):
    id: int
    name: str


class PluggyItem(PluggyModel):
    id: UUID
    connector: PluggyConnector
    status: str
    execution_status: str | None = None
    created_at: datetime
    updated_at: datetime
    last_updated_at: datetime | None = None
    consent_expires_at: datetime | None = None


class PluggyCreditLine(PluggyModel):
    """Item de `creditData.disaggregatedCreditLimits`: o limite do cartão
    quebrado por linha (`LIMITE_CREDITO_TOTAL`, `CREDITO_PARCELADO`, saque...)."""

    line_name: str | None = None
    used_amount: Decimal | None = None


class PluggyCreditData(PluggyModel):
    credit_limit: Decimal | None = None
    available_credit_limit: Decimal | None = None
    brand: str | None = None
    balance_due_date: datetime | None = None
    balance_close_date: datetime | None = None
    minimum_payment: Decimal | None = None
    # `| None`: a Pluggy pode mandar `null` em vez de omitir a chave.
    disaggregated_credit_limits: list[PluggyCreditLine] | None = None


class PluggyAccount(PluggyModel):
    id: UUID
    item_id: UUID
    type: str
    subtype: str | None = None
    number: str | None = None
    name: str | None = None
    currency_code: str
    balance: Decimal
    credit_data: PluggyCreditData | None = None


class PluggyAccountPage(PluggyModel):
    results: list[PluggyAccount]
    page: int
    total: int
    total_pages: int


class PluggyMerchant(PluggyModel):
    name: str | None = None


class PluggyCreditCardMetadata(PluggyModel):
    installment_number: int | None = None
    total_installments: int | None = None


class PluggyPaymentData(PluggyModel):
    """Só o campo que a gente filtra por enquanto — payer/receiver/boleto
    ficam preservados em `raw` mesmo sem schema próprio, via `extra="allow"`."""

    payment_method: str | None = None


class PluggyTransaction(PluggyModel):
    id: UUID
    account_id: UUID
    date: datetime
    description: str
    type: str
    amount: Decimal
    balance: Decimal | None = None
    currency_code: str
    category: str | None = None
    status: str | None = None
    merchant: PluggyMerchant | None = None
    credit_card_metadata: PluggyCreditCardMetadata | None = None
    payment_data: PluggyPaymentData | None = None


class PluggyTransactionPage(PluggyModel):
    results: list[PluggyTransaction]
    next: str | None = None


class PluggyBillFinanceCharge(PluggyModel):
    """`type` é string livre de propósito: a doc lista os valores
    (LATE_PAYMENT_REMUNERATIVE_INTEREST, LATE_PAYMENT_FEE, LATE_PAYMENT_INTEREST,
    IOF, OTHER) só na descrição, não como enum fechado."""

    type: str
    amount: Decimal


class PluggyBill(PluggyModel):
    """Fatura fechada de cartão (`GET /bills`). Valores em reais, não em
    centavos — conferido contra a API em 2026-11-06 (`totalAmount: 2517.59`).
    `payments` fica só no `raw`: PicPay anexa o pagamento à fatura que ele
    quitou, o Free à fatura seguinte (a regra da doc), então o campo não diz
    de forma confiável se ESTA fatura foi paga."""

    id: UUID
    due_date: datetime
    bill_closing_date: datetime | None = None
    total_amount: Decimal
    total_amount_currency_code: str | None = None
    minimum_payment_amount: Decimal | None = None
    finance_charges: list[PluggyBillFinanceCharge] = []


class PluggyBillPage(PluggyModel):
    results: list[PluggyBill]
    page: int
    total: int
    total_pages: int


class PluggyInvestment(PluggyModel):
    """A Pluggy manda dezenas de campos por investimento (taxas, datas,
    rating...) e a gente só precisa de meia dúzia pro schema próprio — o
    resto sobrevive em `raw` só por herdar `extra="allow"` de `PluggyModel`."""

    id: UUID
    item_id: UUID
    type: str
    subtype: str | None = None
    name: str
    balance: Decimal
    status: str | None = None
    issuer: str | None = None


class PluggyInvestmentPage(PluggyModel):
    results: list[PluggyInvestment]
    page: int
    total: int
    total_pages: int
