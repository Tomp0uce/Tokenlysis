from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...api import deps
from ...core.security import AuthenticatedUser
from ...services.files import get_file_service

router = APIRouter(prefix="/files", tags=["files"])


class SignRequest(BaseModel):
    object_name: str = Field(..., pattern=r"^\S+$")
    expires_in: int = Field(ge=1, le=3600)


@router.post("/sign")
async def sign_upload(
    payload: SignRequest,
    _: AuthenticatedUser = Depends(deps.require_role("files", "write")),
):
    service = get_file_service()
    signature = service.create_upload_signature(payload.object_name, payload.expires_in)
    return {"url": signature["url"], "fields": signature["fields"]}
