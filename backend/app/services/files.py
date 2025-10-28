from __future__ import annotations

from datetime import timedelta
from typing import Any

import boto3
from botocore.client import Config

from ..core.config import get_settings


class FileService:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=str(settings.s3_endpoint),
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = settings.s3_bucket

    def create_upload_signature(self, object_name: str, expires_in: int) -> dict[str, Any]:
        fields = {"acl": "private", "success_action_status": "201"}
        conditions: list[Any] = [{"acl": "private"}]
        return self._client.generate_presigned_post(
            Bucket=self._bucket,
            Key=object_name,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expires_in,
        )


def get_file_service() -> FileService:
    return FileService()
