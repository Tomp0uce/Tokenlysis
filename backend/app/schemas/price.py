from pydantic import BaseModel


class PriceResponse(BaseModel):
    coin_id: str
    usd: float


__all__ = ["PriceResponse"]
