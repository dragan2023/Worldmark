from pydantic import BaseModel


class IPTypeOption(BaseModel):
    code: str
    name: str


class IPTypeListResponse(BaseModel):
    items: list[IPTypeOption]
