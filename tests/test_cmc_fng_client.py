from typing import Any

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
        "timestamp": "2024-03-02T01:02:03+00:00",
        "score": 73,
        "label": "Greed",
    }
    assert session.calls == [
        {
            "url": "https://api.example.com/v3/fear-and-greed/latest",
            "params": None,
            "timeout": (3.1, 20),
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
            "timestamp": "2024-02-01T00:00:00+00:00",
            "score": 55,
            "label": "Neutral",
        },
        {
            "timestamp": "2024-02-03T00:00:00+00:00",
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
            "timeout": (3.1, 20),
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
        "timestamp": "2024-03-05T12:00:00+00:00",
        "score": 9,
        "label": "Extreme Fear",
    }


def test_get_historical_returns_empty_for_invalid_data() -> None:
    responses = [DummyResponse({"data": [None, "oops", {"timestamp": ""}]} )]
    session = DummySession(responses)
    client = CoinMarketCapFearGreedClient(api_key=None, base_url=None, session=session, throttle_ms=0)

    history = client.get_historical()
    assert history == []
