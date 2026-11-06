import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    due_date: dt.date
    close_date: dt.date | None
    total_amount: Decimal
    minimum_payment: Decimal | None
    finance_charges_total: Decimal
    currency_code: str
