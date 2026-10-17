import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    subtype: str | None
    name: str | None
    number_masked: str | None
    currency_code: str
    balance: Decimal | None
    credit_limit: Decimal | None
    available_credit_limit: Decimal | None
    brand: str | None
    balance_due_date: dt.date | None
    balance_close_date: dt.date | None
    minimum_payment: Decimal | None
    is_own: bool
    include_in_analysis: bool
    updated_at: dt.datetime
