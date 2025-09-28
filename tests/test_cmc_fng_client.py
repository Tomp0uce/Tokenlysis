from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
import requests

from backend.app.clients.cmc_fng import CoinMarketCapFearGreedClient


class DummyResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self) -> Any:
        return self._payload


class DummySession:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: tuple[float, float] | None = None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        try:
            return self.responses.pop(0)
        except IndexError as exc:  # pragma: no cover - defensive guard
            raise AssertionError("unexpected request") from exc


def test_get_latest_normalizes_payload() -> None:
    responses = [
        DummyResponse(
            {
                "data": [
                    {
                        "timestamp": "2024-03-01T00:00:00.000Z",
                        "value": "45.4",
                        "value_classification": "Neutral",
                        "extra": "ignored",
                    },
                    {
                        "timestamp": "2024-03-02T01:02:03Z",
                        "value": 72.6,
                        "value_classification": "Greed",
                    },
                ]
            }
        )
    ]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(
        api_key="secret",
        base_url="https://api.example.com",
        session=session,
        throttle_ms=0,
    )

    latest = client.get_latest()
    assert latest == {
        "timestamp": "2024-03-02T01:02:03Z",
        "score": 73,
        "label": "Greed",
    }
    assert session.calls == [
        {
            "url": "https://api.example.com/v3/fear-and-greed/latest",
            "params": None,
            "timeout": (5, 5),
        }
    ]
    assert session.headers["Accept"] == "application/json"
    assert session.headers["X-CMC_PRO_API_KEY"] == "secret"


def test_get_historical_includes_params_and_filters() -> None:
    responses = [
        DummyResponse(
            {
                "data": [
                    {
                        "timestamp": "2024-02-01T00:00:00Z",
                        "value": 55,
                        "value_classification": "Neutral",
                    },
                    {
                        "timestamp": None,
                        "value": 18,
                    },
                    {
                        "timestamp": "2024-02-03T00:00:00Z",
                        "value": 110,
                        "value_classification": "Extreme Greed",
                    },
                ]
            }
        )
    ]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(
        api_key=None,
        base_url="https://api.example.com",
        session=session,
        throttle_ms=0,
    )

    history = client.get_historical(limit=3, time_start="2024-02-01T00:00:00Z", time_end="2024-02-28T00:00:00Z")
    assert history == [
        {
            "timestamp": "2024-02-01T00:00:00Z",
            "score": 55,
            "label": "Neutral",
        },
        {
            "timestamp": "2024-02-03T00:00:00Z",
            "score": 100,
            "label": "Extreme Greed",
        },
    ]
    assert session.calls == [
        {
            "url": "https://api.example.com/v3/fear-and-greed/historical",
            "params": {
                "limit": 3,
                "time_start": "2024-02-01T00:00:00Z",
                "time_end": "2024-02-28T00:00:00Z",
            },
            "timeout": (5, 5),
        }
    ]


def test_get_latest_handles_dict_payload() -> None:
    responses = [
        DummyResponse(
            {
                "data": {
                    "timestamp": "2024-03-05T12:00:00Z",
                    "value": "9.2",
                    "value_classification": "Extreme Fear",
                }
            }
        )
    ]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(api_key=None, base_url=None, session=session, throttle_ms=0)

    latest = client.get_latest()
    assert latest == {
        "timestamp": "2024-03-05T12:00:00Z",
        "score": 9,
        "label": "Extreme Fear",
    }


def test_get_latest_supports_update_time_payload() -> None:
    responses = [
        DummyResponse(
            {
                "data": {
                    "value": 34,
                    "update_time": "2025-09-28T10:23:10.053Z",
                    "value_classification": "Fear",
                }
            }
        )
    ]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(api_key=None, base_url=None, session=session, throttle_ms=0)

    latest = client.get_latest()
    assert latest == {
        "timestamp": "2025-09-28T10:23:10.053000Z",
        "score": 34,
        "label": "Fear",
    }


def test_get_historical_returns_empty_for_invalid_data() -> None:
    responses = [DummyResponse({"data": [None, "oops", {"timestamp": ""}]})]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(api_key=None, base_url=None, session=session, throttle_ms=0)

    history = client.get_historical()
    assert history == []


def test_get_historical_parses_numeric_timestamps() -> None:
    responses = [
        DummyResponse(
            {
                "data": [
                    {
                        "timestamp": "1758931200",
                        "value": 34,
                        "value_classification": "Fear",
                    },
                    {
                        "timestamp": "1758844800",
                        "value": 32,
                        "value_classification": "Fear",
                    },
                    {
                        "timestamp": "1758758400",
                        "value": 41,
                        "value_classification": "Neutral",
                    },
                ]
            }
        )
    ]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(api_key=None, base_url=None, session=session, throttle_ms=0)

    history = client.get_historical()
    assert history == [
        {
            "timestamp": "2025-09-25T00:00:00Z",
            "score": 41,
            "label": "Neutral",
        },
        {
            "timestamp": "2025-09-26T00:00:00Z",
            "score": 32,
            "label": "Fear",
        },
        {
            "timestamp": "2025-09-27T00:00:00Z",
            "score": 34,
            "label": "Fear",
        },
    ]


def test_get_latest_accepts_unix_timestamp() -> None:
    epoch = dt.datetime(2024, 9, 21, tzinfo=dt.timezone.utc)
    responses = [
        DummyResponse(
            {
                "data": [
                    {
                        "timestamp": epoch.timestamp(),
                        "score": 49.4,
                        "value_classification": "Neutral",
                    }
                ]
            }
        )
    ]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(
        api_key=None, base_url="https://api.example.com", session=session, throttle_ms=0
    )

    latest = client.get_latest()
    assert latest == {
        "timestamp": epoch.isoformat(),
        "score": 49,
        "label": "Neutral",
    }


def test_request_retries_with_backoff_and_logging(monkeypatch, caplog) -> None:
    failure = DummyResponse({"status": "error"}, status_code=502)
    success = DummyResponse({"data": {"timestamp": "2024-01-01T00:00:00Z", "value": 42}})
    session = DummySession([failure, failure, success])

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr("time.sleep", fake_sleep)

    client = CoinMarketCapFearGreedClient(
        api_key=None,
        base_url="https://api.example.com",
        session=session,
        throttle_ms=0,
    )

    with caplog.at_level("WARNING"):
        latest = client.get_latest()

    assert latest == {
        "timestamp": "2024-01-01T00:00:00Z",
        "score": 42,
        "label": "Unknown",
    }

    assert len(session.calls) == 3
    assert sleep_calls[:2] == [pytest.approx(0.25, rel=0, abs=1e-6), pytest.approx(0.5, rel=0, abs=1e-6)]

    error_logs = [record for record in caplog.records if "coinmarketcap request failed" in record.getMessage()]
    assert error_logs, "expected at least one error log"
    message = error_logs[0].getMessage()
    assert "/v3/fear-and-greed/latest" in message
    assert "502" in message
