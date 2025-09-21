import json
import logging
import time
from typing import List
from urllib.parse import urlparse

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
            "price_change_percentage": "24h,7d,30d",
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

    @staticmethod
    def _clean_url(value: str | None) -> str | None:
        if not value or not isinstance(value, str):
            return None
        candidate = value.strip()
        if not candidate:
            return None
        parsed = urlparse(candidate)
        if not parsed.scheme:
            candidate = f"https://{candidate}"
            parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return candidate

    @staticmethod
    def _build_twitter_url(handle: str | None) -> str | None:
        if not handle or not isinstance(handle, str):
            return None
        cleaned = handle.strip().lstrip("@")
        if not cleaned:
            return None
        return f"https://twitter.com/{cleaned}"

    def _extract_links(self, payload: dict) -> dict[str, str]:
        links: dict[str, str] = {}
        homepage = payload.get("homepage")
        if isinstance(homepage, list):
            for candidate in homepage:
                cleaned = self._clean_url(candidate)
                if cleaned:
                    links["website"] = cleaned
                    break
        twitter_url = self._clean_url(self._build_twitter_url(payload.get("twitter_screen_name")))
        if twitter_url:
            links["twitter"] = twitter_url
        reddit_url = self._clean_url(payload.get("subreddit_url"))
        if reddit_url:
            links["reddit"] = reddit_url
        repos = payload.get("repos_url")
        if isinstance(repos, dict):
            github_list = repos.get("github")
            if isinstance(github_list, list):
                for candidate in github_list:
                    cleaned = self._clean_url(candidate)
                    if cleaned:
                        links["github"] = cleaned
                        break
        chat_urls = payload.get("chat_url")
        chat_candidates = chat_urls if isinstance(chat_urls, list) else []
        for candidate in chat_candidates:
            cleaned = self._clean_url(candidate)
            if cleaned and "discord" in cleaned.lower():
                links.setdefault("discord", cleaned)
            if cleaned and any(host in cleaned.lower() for host in ("t.me", "telegram.", "telegram.me")):
                links.setdefault("telegram", cleaned)
        if "telegram" not in links:
            identifier = payload.get("telegram_channel_identifier")
            if isinstance(identifier, str):
                handle = identifier.strip().lstrip("@")
                if handle:
                    constructed = self._clean_url(f"https://t.me/{handle}")
                    if constructed:
                        links["telegram"] = constructed
        return links

    def get_coin_profile(self, coin_id: str) -> dict[str, object]:
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
            categories = [c for c in cats if isinstance(c, str)] if isinstance(cats, list) else []
            links_payload = data.get("links") if isinstance(data.get("links"), dict) else {}
            links = self._extract_links(links_payload)
            return {"categories": categories, "links": links}
        except requests.HTTPError as exc:  # pragma: no cover - defensive
            logger.warning("coin profile fetch failed for %s: %s", coin_id, exc)
        return {"categories": [], "links": {}}

    def get_coin_categories(self, coin_id: str) -> list[str]:
        profile = self.get_coin_profile(coin_id)
        return profile.get("categories", [])

    def get_categories_list(self) -> list[dict]:
        try:
            return self._request("/coins/categories/list").json()
        except requests.HTTPError as exc:  # pragma: no cover - defensive
            logger.warning("categories list fetch failed: %s", exc)
            return []
