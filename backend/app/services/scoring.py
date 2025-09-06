import math
from typing import List, Optional


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    k = (len(vals) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    d0 = vals[f] * (c - k)
    d1 = vals[c] * (k - f)
    return d0 + d1


def _normalize(values: List[float], log: bool = False) -> List[int]:
    """Generic normalization to 0-100 with optional log10 transform."""
    if log:
        vals = [math.log10(max(v, 1e-12)) for v in values]
    else:
        vals = list(values)
    p5 = _percentile(vals, 5)
    p95 = _percentile(vals, 95)
    denom = p95 - p5 or 1.0
    scores = []
    for v in vals:
        vp = min(max(v, p5), p95)
        s = round(100 * (vp - p5) / denom)
        scores.append(s)
    return scores


def score_liquidite(
    volume: List[float], market_cap: List[float], listings: List[int]
) -> List[int]:
    sv = _normalize(volume, log=True)
    sm = _normalize(market_cap, log=True)
    sl = _normalize(listings, log=False)
    return [
        round(0.45 * v + 0.35 * m + 0.20 * listing) for v, m, listing in zip(sv, sm, sl)
    ]


def score_opportunite(rsi: List[float], vol_change: List[float]) -> List[int]:
    s_rsi = [max(0.0, min((70 - v) / 40.0, 1.0)) for v in rsi]
    s_vol = [x / 100 for x in _normalize(vol_change, log=False)]
    return [round(100 * (0.60 * r + 0.40 * v)) for r, v in zip(s_rsi, s_vol)]


def score_global(
    liq: List[Optional[int]], opp: List[Optional[int]]
) -> List[Optional[int]]:
    res: List[Optional[int]] = []
    for liq_score, opp_score in zip(liq, opp):
        parts = [p for p in (liq_score, opp_score) if p is not None]
        if not parts:
            res.append(None)
        else:
            res.append(round(sum(parts) / len(parts)))
    return res


__all__ = [
    "_normalize",
    "score_liquidite",
    "score_opportunite",
    "score_global",
]
