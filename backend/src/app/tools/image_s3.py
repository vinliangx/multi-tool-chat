from __future__ import annotations

import base64
import csv
import io
import os

import boto3
from botocore.client import Config
from pydantic import BaseModel, Field

from app.agent.vision import vision
from app.config import settings
from app.tools.base import make_session_tool


class ImageReadArgs(BaseModel):
    prompt: str = Field(..., description="The user prompt")
    source: str = Field(
        ...,
        description="Reads an s3://bucket/key URL",
    )


async def _run(prompt: str, source: str) -> str:
    assert source.startswith("s3://")
    try:
        _, _, rest = source.partition("s3://")

        bucket, _, key = rest.partition("/")

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.internal_s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.region_name,
            config=Config(signature_version="s3v4"),
        )
        obj = s3.get_object(Bucket=bucket, Key=key)
        mime_type = obj["ContentType"]
        object_content = obj["Body"].read()
        encoded_string = base64.b64encode(object_content).decode("utf-8")
        result = await vision(prompt=prompt, mime=mime_type, data=encoded_string)
        return f"Image Result: {result}"
    except Exception as e:
        return f"Error : {e}"


def factory(session_id_provider):
    return make_session_tool(
        name="image_read",
        description="Read a Image file from S3 (s3://bucket/key)",
        args_schema=ImageReadArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
