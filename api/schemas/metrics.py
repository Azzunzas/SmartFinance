from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from core.analysis.health import HealthStatus


class AccountBalanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    name: str | None
    type: str
    subtype: str | None
    balance: Decimal | None


class OverviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    accounts: list[AccountBalanceOut]
    open_credit_card_bill: Decimal
    investments_balance: Decimal
    net_worth: Decimal


class PlannedVsActualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    planned_item_id: int
    name: str
    kind: str
    category_id: int | None
    expected_amount: Decimal
    tolerance_pct: Decimal
    matched_amount: Decimal


class MonthlyCashflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: str
    total_in: Decimal
    total_out: Decimal
    net: Decimal


class NetWorthPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    net_worth: Decimal


class CategorySpendDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    total: Decimal


class CategorySpendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    name: str
    total: Decimal
    details: list[CategorySpendDetailOut]


class FinancialHealthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference_months: list[str]
    available_cash: Decimal
    savings_rate: Decimal | None
    burn_rate: Decimal | None
    runway_months: Decimal | None
    fixed_cost_monthly: Decimal | None
    safety_margin: Decimal | None
    score: int | None
    status: HealthStatus | None
    bill_coverage: Decimal | None
    net_worth_trend: Decimal | None
