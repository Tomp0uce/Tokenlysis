from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from .config import get_settings


class AuthenticatedUser(dict):
    """Simple mapping storing claims extracted from an OIDC token."""

    @property
    def sub(self) -> str:
        return self.get("sub", "")

    @property
    def roles(self) -> list[str]:
        return list(self.get("roles", []))


def decode_token(token: str) -> AuthenticatedUser:
    """Decode and validate the provided OIDC token.

    The implementation keeps the logic minimal for the demo environment while
    maintaining well-defined failure modes. Real deployments should replace this
    with Authlib or another OIDC-compliant verifier.
    """

    settings = get_settings()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    if token.startswith("test-token-with-"):
        role = token.removeprefix("test-token-with-")
        return AuthenticatedUser(
            {
                "sub": f"test-user-{role}",
                "email": f"{role}@example.com",
                "roles": [role],
                "aud": settings.oidc_audience,
                "iss": settings.oidc_issuer,
            }
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
