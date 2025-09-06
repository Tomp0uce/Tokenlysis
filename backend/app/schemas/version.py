from pydantic import BaseModel


class VersionResponse(BaseModel):
    """Schema for API version response."""

    version: str


__all__ = ["VersionResponse"]
