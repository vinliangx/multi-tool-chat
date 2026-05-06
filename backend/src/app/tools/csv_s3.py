from __future__ import annotations

import csv
import io
import os

import boto3
from botocore.client import Config
from pydantic import BaseModel, Field

from app.config import settings
from app.tools.base import make_session_tool


class CsvReadArgs(BaseModel):
    source: str = Field(
        ...,
        description="Reads an s3://bucket/key URL",
    )
    max_rows: int = Field(500, description="Cap on rows to load")


async def _run(source: str, max_rows: int = 500) -> str:
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
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")

        reader = csv.reader(io.StringIO(body))
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                rows.append(["... [truncated]"])
                break
            rows.append(row)

        out = io.StringIO()
        csv.writer(out).writerows(rows)
        return f"CSV from {source} ({len(rows)} rows shown)\n\n{out.getvalue()}"
    except Exception as e:
        return f"Error : {e}"


def factory(session_id_provider):
    return make_session_tool(
        name="csv_read",
        description="Read a CSV file from S3 (s3://bucket/key)",
        args_schema=CsvReadArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
