from __future__ import annotations

from fastapi import APIRouter, Depends

from ...api import deps
from ...core.security import AuthenticatedUser
from ...tasks.recalculate import recalculate_scores

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/recalculate", status_code=202)
async def schedule_recalculation(
    _: AuthenticatedUser = Depends(deps.require_role("tasks", "write")),
) -> dict[str, str]:
    recalculate_scores.send()
    return {"status": "scheduled"}
