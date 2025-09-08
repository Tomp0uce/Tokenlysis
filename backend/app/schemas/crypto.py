from typing import List

from pydantic import BaseModel, Field, ConfigDict


class Scores(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_: float = Field(..., alias="global")
    liquidite: float
    opportunite: float


class Latest(BaseModel):
    date: str
    price_usd: float | None = None
    metrics: dict[str, float] | None = None
    scores: Scores


class CryptoSummary(BaseModel):
    id: int
    symbol: str
    name: str
    sectors: List[str]
    category_names: List[str] = Field(default_factory=list)
    category_ids: List[str] = Field(default_factory=list)
    latest: Latest


class RankingResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CryptoSummary]


class CryptoDetail(BaseModel):
    id: int
    symbol: str
    name: str
    sectors: List[str]
    category_names: List[str] = Field(default_factory=list)
    category_ids: List[str] = Field(default_factory=list)
    latest: Latest


class HistoryPoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str


class HistoryResponse(BaseModel):
    series: List[HistoryPoint]
