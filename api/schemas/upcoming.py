from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MonthlyCommitmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period: str
    pending_total: Decimal
    installments_total: Decimal
    bills_total: Decimal
    total: Decimal
