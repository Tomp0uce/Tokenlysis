from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api import deps
from ...core.security import AuthenticatedUser

router = APIRouter(prefix="/scores", tags=["scores"])


def _mock_scores() -> list[dict[str, float | str]]:
    return [
        {"coin": "btc", "score": 0.91},
        {"coin": "eth", "score": 0.87},
        {"coin": "sol", "score": 0.84},
    ]


@router.get("")
async def list_scores(
    _: AuthenticatedUser = Depends(deps.require_role("stream", "read")),
) -> list[dict[str, float | str]]:
    return _mock_scores()
