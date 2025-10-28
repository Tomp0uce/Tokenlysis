from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api import deps
from ...core.security import AuthenticatedUser
from ...models.user import User
from ...schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(deps.get_db),
    _: AuthenticatedUser = Depends(deps.require_role("users", "write")),
) -> list[UserRead]:
    result = await db.execute(select(User))
    return [UserRead.model_validate(user) for user in result.scalars().all()]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(deps.get_db),
    _: AuthenticatedUser = Depends(deps.require_role("users", "write")),
) -> UserRead:
    user = User(email=payload.email, full_name=payload.full_name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:  # pragma: no cover
        await db.rollback()
        raise exc
    await db.refresh(user)
    return UserRead.model_validate(user)
