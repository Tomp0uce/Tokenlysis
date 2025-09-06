from typing import Iterable, List

def rsi(prices: Iterable[float], period: int = 14) -> List[float]:
    prices = list(prices)
    n = len(prices)
    if n < 2:
        return [0.0] * n
    use_period = min(period, n - 1)
    gains = []
    losses = []
    for i in range(1, use_period + 1):
        diff = prices[i] - prices[i - 1]
        if diff >= 0:
            gains.append(diff)
        else:
            losses.append(-diff)
    avg_gain = sum(gains) / use_period
    avg_loss = sum(losses) / use_period
    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    rsi_values = [100 - 100 / (1 + rs)]
    for i in range(use_period + 1, n):
        diff = prices[i] - prices[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (use_period - 1) + gain) / use_period
        avg_loss = (avg_loss * (use_period - 1) + loss) / use_period
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        rsi_values.append(100 - 100 / (1 + rs))
    prefix = [0.0] * (n - len(rsi_values))
    return prefix + rsi_values

__all__ = ["rsi"]
