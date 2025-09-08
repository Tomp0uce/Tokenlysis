from typing import List

from pydantic import BaseModel, Field


class PriceResponse(BaseModel):
    coin_id: str
    usd: float
    category_names: List[str] = Field(default_factory=list)
    category_ids: List[str] = Field(default_factory=list)


__all__ = ["PriceResponse"]
