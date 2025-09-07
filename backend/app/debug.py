from __future__ import annotations

# DEBUG: temporary debug utilities

from subprocess import run

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .core.settings import settings
from .services.coingecko import CoinGeckoClient


def get_coingecko_client() -> CoinGeckoClient:  # DEBUG: local copy
    return CoinGeckoClient()


router = APIRouter()


class DebugInfo(BaseModel):
    coingecko_command: str
    api_key: str | None
    ping_command: str
    ping_response: str


@router.get("/debug", response_model=DebugInfo)
# DEBUG: endpoint exposing internal commands
async def get_debug_info(
    client: CoinGeckoClient = Depends(get_coingecko_client),
) -> DebugInfo:
    limit = settings.cg_top_n
    url = (
        f"{client.base_url}/coins/markets?vs_currency=usd&order=market_cap_desc"
        f"&per_page={limit}&page=1"
    )
    api_key = client.api_key
    header = f"-H 'x-cg-pro-api-key: {api_key}' " if api_key else ""
    coingecko_command = f"curl {header}'{url}'"

    ping_command = "ping -c 1 api.coingecko.com"
    proc = run(ping_command.split(), capture_output=True, text=True)
    ping_response = proc.stdout or proc.stderr

    return DebugInfo(
        coingecko_command=coingecko_command,
        api_key=api_key,
        ping_command=ping_command,
        ping_response=ping_response,
    )


__all__ = ["router"]
