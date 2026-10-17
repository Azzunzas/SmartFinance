from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
