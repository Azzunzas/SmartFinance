from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class InvestmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str | None
    subtype: str | None
    issuer: str | None
    status: str | None
    is_active: bool
    balance: Decimal | None
