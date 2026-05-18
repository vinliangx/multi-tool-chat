import csv
import io

import boto3
from botocore.client import Config
from pydantic import BaseModel, Field

from app.config import settings
from app.tools.plugin import ToolContext, ToolPlugin


class CsvReadArgs(BaseModel):
    source: str = Field(..., description="Reads an s3://bucket/key URL")
    max_rows: int = Field(
        200, description="Cap on rows to return when no filter is applied, max is 200"
    )
    filter_column: str | None = Field(None, description="Column name to filter on")
    filter_value: str | None = Field(
        None, description="Case-insensitive substring to match in filter_column"
    )


class CsvS3Plugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "csv_read"

    @property
    def description(self) -> str:
        return (
            "Read a CSV file from S3 (s3://bucket/key). "
            "Use filter_column + filter_value to search ALL rows when looking for specific values; "
            "without a filter, only the first max_rows rows are returned."
            "Data may be incomplete if truncated and may have missing information"
        )

    @property
    def args_schema(self) -> type[BaseModel]:
        return CsvReadArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        source = kwargs["source"]
        max_rows = kwargs.get("max_rows", 100)
        filter_column = kwargs.get("filter_column")
        filter_value = kwargs.get("filter_value")

        if max_rows > 200:
            return "Error: 200 lines is the max request"

        if not source.startswith("s3://"):
            return "Error: source must start with s3://"

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
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        finally:
            s3.close()

        reader = csv.DictReader(io.StringIO(body))
        fieldnames = reader.fieldnames or []

        filtering = filter_column is not None and filter_value is not None

        if filtering and filter_column not in fieldnames:
            return (
                f"Error: column '{filter_column}' not found. "
                f"Available columns: {', '.join(fieldnames)}"
            )

        total_rows = 0
        matched_rows: list[dict] = []
        unfiltered_rows: list[dict] = []
        truncated = False

        needle = filter_value.lower() if filter_value else ""

        for row in reader:
            total_rows += 1
            if filtering:
                if needle in row.get(filter_column, "").lower():
                    matched_rows.append(row)
            else:
                if len(unfiltered_rows) < max_rows:
                    unfiltered_rows.append(row)
                else:
                    truncated = True

        if filtering:
            rows_to_show = matched_rows
            header = (
                f"CSV from {source} — filtered '{filter_value}' in column '{filter_column}': "
                f"{len(matched_rows)} matching rows out of {total_rows} total rows scanned.\n\n"
            )
        else:
            rows_to_show = unfiltered_rows
            if truncated:
                header = (
                    f"WARNING: CSV has {total_rows} rows but only the first {max_rows} are shown. "
                    f"Results below are INCOMPLETE. To search the full dataset use filter_column "
                    f"and filter_value parameters.\n\n"
                    f"CSV from {source} ({max_rows} of {total_rows} rows shown)\n\n"
                )
            else:
                header = f"CSV from {source} ({total_rows} rows)\n\n"

        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_to_show)
        return header + out.getvalue()
