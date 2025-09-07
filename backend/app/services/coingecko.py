import json
import logging
import random
import time
from typing import List

import requests

from ..core.settings import settings, mask_secret

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoClient:
    """HTTP client for the CoinGecko API with throttling and retries."""

    def __init__(
        self,
        api_key: str | None,
        plan: str = "demo",
        base_url: str = BASE_URL,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.plan = plan
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "Tokenlysis/1.0"}
        )
        if api_key:
            header_name = "x-cg-pro-api-key" if plan == "pro" else "x-cg-demo-api-key"
            self.session.headers.update({header_name: api_key})
            masked = mask_secret(api_key)
            logger.info("CoinGecko auth header set: %s=%s", header_name, masked)
        self.api_key = api_key

    def _request(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.base_url}{path}"
        time.sleep(settings.CG_THROTTLE_MS / 1000.0)
        for attempt in range(6):
            t0 = time.perf_counter()
            resp = self.session.get(url, params=params, timeout=(3.1, 20))
            latency = int((time.perf_counter() - t0) * 1000)
            rid = resp.headers.get("X-Request-Id", "-")
            sent_demo = "x-cg-demo-api-key" in resp.request.headers
            logger.info(
                json.dumps(
                    {
                        "endpoint": path,
                        "url": resp.url,
                        "status": resp.status_code,
                        "latency_ms": latency,
                        "retries": attempt,
                        "plan": self.plan,
                        "sent_demo_header": sent_demo,
                        "request_id": rid,
                    }
                )
            )
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After")
                if ra:
                    wait = float(ra)
                else:
                    wait = min(0.5 * (2**attempt), 8)
                    wait += random.uniform(0, 0.1)
                time.sleep(wait)
                continue
            try:
                resp.raise_for_status()
                return resp
            except requests.HTTPError:
                logger.error(
                    "CG error %s %s params=%s body=%s",
                    resp.status_code,
                    url,
                    params,
                    resp.text[:500],
                )
                raise
        resp.raise_for_status()
        return resp

    def ping(self) -> str:
        return self._request("/ping").json().get("gecko_says", "")

    def get_simple_price(self, coin_ids: List[str], vs_currencies: List[str]) -> dict:
        params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
        return self._request("/simple/price", params).json()

    def get_markets(
        self,
        vs: str = "usd",
        order: str = "market_cap_desc",
        per_page: int = 20,
        page: int = 1,
    ) -> List[dict]:
        params = {
            "vs_currency": vs,
            "order": order,
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }
        return self._request("/coins/markets", params).json()

    def get_market_chart(self, coin_id: str, days: int, vs: str = "usd") -> dict:
        now = int(time.time())
        start = now - days * 86400
        params = {
            "vs_currency": vs,
            "from": start,
            "to": now,
            "interval": "daily",
        }
        return self._request(
            f"/coins/{coin_id.lower()}/market_chart/range", params
        ).json()
