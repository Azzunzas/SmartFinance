from datetime import date
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from core.analysis.planned_matching import MatchType, PlannedKind


class _RuleFields(BaseModel):
    """Campos comuns a `RulePreviewRequest` e `PlannedItemRuleCreate` — os
    dois testam a mesma regra, um sem salvar e o outro salvando."""

    match_type: MatchType
    pattern: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account_id: int | None = None

    @model_validator(mode="after")
    def _validate_fields_for_match_type(self) -> Self:
        if self.match_type in (MatchType.CONTAINS, MatchType.REGEX, MatchType.MERCHANT):
            if not self.pattern:
                raise ValueError(f"match_type {self.match_type} exige `pattern`")
        if self.match_type is MatchType.AMOUNT_RANGE:
            if self.amount_min is None or self.amount_max is None:
                raise ValueError("match_type AMOUNT_RANGE exige `amount_min` e `amount_max`")
            if self.amount_min > self.amount_max:
                raise ValueError("`amount_min` deve ser menor ou igual a `amount_max`")
        return self


class RulePreviewRequest(_RuleFields):
    """Regra ainda não salva, testada contra o histórico (doc §6.2)."""


class RulePreviewMatch(BaseModel):
    transaction_id: int
    description: str
    accrual_date: date
    amount_abs: Decimal
    period: str


class RulePreviewResponse(BaseModel):
    matched_count: int
    matches: list[RulePreviewMatch]


class PlannedItemRuleCreate(_RuleFields):
    priority: int = 100


class PlannedItemRuleUpdate(BaseModel):
    """PATCH — todo campo é opcional; só o que vier no corpo é atualizado.
    Sem a validação cruzada de `_RuleFields` (exigiria ler o resto da linha
    já salva pra saber se o `match_type` final é consistente); valida só o
    que dá pra checar olhando só pro corpo da request."""

    match_type: MatchType | None = None
    pattern: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account_id: int | None = None
    priority: int | None = None

    @model_validator(mode="after")
    def _validate_amount_bounds(self) -> Self:
        if self.amount_min is not None and self.amount_max is not None:
            if self.amount_min > self.amount_max:
                raise ValueError("`amount_min` deve ser menor ou igual a `amount_max`")
        return self


class PlannedItemRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    planned_item_id: int
    match_type: MatchType
    pattern: str | None
    amount_min: Decimal | None
    amount_max: Decimal | None
    account_id: int | None
    priority: int


class PlannedItemCreate(BaseModel):
    name: str
    kind: PlannedKind
    category_id: int | None = None
    expected_amount: Decimal
    tolerance_pct: Decimal = Decimal("10.0")
    expected_day: int | None = None
    day_tolerance: int = 5
    valid_from: date
    valid_to: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("`valid_to` deve ser maior ou igual a `valid_from`")
        return self


class PlannedItemUpdate(BaseModel):
    name: str | None = None
    kind: PlannedKind | None = None
    category_id: int | None = None
    expected_amount: Decimal | None = None
    tolerance_pct: Decimal | None = None
    expected_day: int | None = None
    day_tolerance: int | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_to < self.valid_from
        ):
            raise ValueError("`valid_to` deve ser maior ou igual a `valid_from`")
        return self


class PlannedItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: PlannedKind
    category_id: int | None
    expected_amount: Decimal
    tolerance_pct: Decimal
    expected_day: int | None
    day_tolerance: int
    valid_from: date
    valid_to: date | None
    is_active: bool
