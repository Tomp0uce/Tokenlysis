import json
import logging
import time
from typing import List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "Tokenlysis/1.0"}
        )
        if api_key:
            header_name = "x-cg-demo-api-key" if plan == "demo" else "x-cg-api-key"
            self.session.headers.update({header_name: api_key})
            masked = mask_secret(api_key)
            logger.info("CoinGecko auth header set: %s=%s", header_name, masked)
        self.api_key = api_key
        throttle = settings.CG_THROTTLE_MS
        if plan == "demo" and throttle < 2100:
            logger.warning(
                "CG_THROTTLE_MS %s too low for demo plan; using 2100 ms", throttle
            )
            throttle = 2100
        self.throttle_ms = throttle

    def _request(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.base_url}{path}"
        time.sleep(self.throttle_ms / 1000.0)
        params_local = params.copy() if params else None
        for attempt in range(2):
            t0 = time.perf_counter()
            resp = self.session.get(url, params=params_local, timeout=(3.1, 20))
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
            if (
                resp.status_code == 401
                and params_local
                and params_local.get("interval") == "daily"
            ):
                try:
                    body = resp.json()
                except Exception:  # pragma: no cover - defensive
                    body = {}
                if body.get("error_code") == 10005:
                    params_local = {
                        k: v for k, v in params_local.items() if k != "interval"
                    }
                    continue
            resp.raise_for_status()
            return resp
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

    def get_market_chart(
        self,
        coin_id: str,
        days: int,
        vs: str = "usd",
        interval: str | None = None,
    ) -> dict:
        if self.plan == "demo":
            time.sleep(2.1)
        params = {"vs_currency": vs, "days": days}
        if interval and interval != "daily":
            params["interval"] = interval
        return self._request(
            f"/coins/{coin_id.lower()}/market_chart", params=params
        ).json()

    def get_market_chart_range(
        self,
        coin_id: str,
        vs: str,
        ts_from: int,
        ts_to: int,
        interval: str | None = None,
    ) -> dict:
        if self.plan == "demo":
            time.sleep(2.1)
        params = {"vs_currency": vs, "from": ts_from, "to": ts_to}
        if interval and interval != "daily":
            params["interval"] = interval
        return self._request(
            f"/coins/{coin_id.lower()}/market_chart/range", params=params
        ).json()

    def get_coin_categories(self, coin_id: str) -> list[str]:
        params = {
            "localization": "false",
            "tickers": "false",
            "market_data": "false",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        }
        try:
            data = self._request(f"/coins/{coin_id.lower()}", params=params).json()
            cats = data.get("categories", [])
            if isinstance(cats, list):
                return [c for c in cats if isinstance(c, str)]
        except requests.HTTPError as exc:  # pragma: no cover - defensive
            logger.warning("coin categories fetch failed for %s: %s", coin_id, exc)
        return []

    def get_categories_list(self) -> list[dict]:
        try:
            return self._request("/coins/categories/list").json()
        except requests.HTTPError as exc:  # pragma: no cover - defensive
            logger.warning("categories list fetch failed: %s", exc)
            return []
