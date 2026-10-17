import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.models.transaction import Direction, TxStatus


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    account_name: str | None
    date: dt.date
    accrual_date: dt.date
    description: str
    merchant_name: str | None
    amount: Decimal
    amount_abs: Decimal
    direction: Direction
    status: TxStatus
    installment_number: int | None
    installment_total: int | None
    payment_method: str | None
    category_id: int | None
    category_name: str | None
    category_id_auto: int | None
    category_id_manual: int | None
    is_internal_transfer: bool
    is_internal_transfer_auto: bool
    is_internal_transfer_manual: bool | None
    is_card_payment: bool
    is_card_payment_auto: bool
    is_card_payment_manual: bool | None
    exclude_from_analysis: bool
    note: str | None


class TransactionPageOut(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None


ClassificationOverrideField = Literal[
    "category_id", "is_internal_transfer", "is_card_payment", "counterpart_tx_id"
]


class _RejectsResetOfFieldBeingSet(BaseModel):
    """Recusa um corpo que manda um valor e pede reset do MESMO campo.

    `{"category_id": 5, "reset_fields": ["category_id"]}` é contraditório: um
    diz "passa a valer 5", o outro diz "volta a seguir o automático". O
    repositório resolvia isso escolhendo o reset e descartando o 5 em silêncio —
    o usuário via a categoria voltar ao automático sem entender por quê.

    Preferir 422 a escolher sozinho: o corpo está errado, e devolver erro é a
    única resposta que não inventa intenção.
    """

    @model_validator(mode="after")
    def _reject_conflicting_reset(self) -> _RejectsResetOfFieldBeingSet:
        enviados = self.model_fields_set
        conflitos = sorted(f for f in self.reset_fields if f in enviados)  # type: ignore[attr-defined]
        if conflitos:
            raise ValueError(
                "não dá pra mandar valor e pedir reset do mesmo campo: "
                + ", ".join(conflitos)
            )
        return self


class TransactionClassificationUpdate(_RejectsResetOfFieldBeingSet):
    """PATCH — todo campo é opcional; só o que vier no corpo é atualizado."""

    category_id: int | None = None
    is_internal_transfer: bool | None = None
    is_card_payment: bool | None = None
    exclude_from_analysis: bool | None = None
    counterpart_tx_id: int | None = None
    note: str | None = None
    reset_fields: list[ClassificationOverrideField] = Field(default_factory=list)


class BulkClassifyRequest(_RejectsResetOfFieldBeingSet):
    """Mesma ideia do PATCH único, aplicada a vários ids de uma vez. Sem
    `counterpart_tx_id`: não faz sentido o mesmo par pra transações diferentes."""

    transaction_ids: list[int]
    category_id: int | None = None
    is_internal_transfer: bool | None = None
    is_card_payment: bool | None = None
    exclude_from_analysis: bool | None = None
    note: str | None = None
    reset_fields: list[ClassificationOverrideField] = Field(default_factory=list)


class BulkClassifyResponse(BaseModel):
    updated_ids: list[int]
    missing_ids: list[int]


class TransactionClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    category_id: int | None
    is_internal_transfer: bool
    is_card_payment: bool
    exclude_from_analysis: bool
    counterpart_tx_id: int | None
    note: str | None
    updated_at: dt.datetime
