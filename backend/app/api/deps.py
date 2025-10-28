from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from ..core import rbac
from ..core.security import AuthenticatedUser, decode_token
from ..db.session import get_session


async def get_db():
    async with get_session() as session:
        yield session


async def get_current_user(authorization: str = Header(..., alias="Authorization")) -> AuthenticatedUser:
    token = authorization.removeprefix("Bearer ")
    return decode_token(token)


def require_role(resource: str, action: str):
    async def dependency(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        for role in user.roles:
            if rbac.authorize(role, resource, action):
                return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return dependency
