import base64

import boto3
from botocore.client import Config
from pydantic import BaseModel, Field

from app.agent.vision import vision
from app.config import settings
from app.tools.plugin import ToolContext, ToolPlugin


class ImageReadArgs(BaseModel):
    prompt: str = Field(..., description="The user prompt")
    source: str = Field(..., description="Reads an s3://bucket/key URL")


class ImageS3Plugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "image_read"

    @property
    def description(self) -> str:
        return "Read a Image file from S3 (s3://bucket/key), OCR Supported."

    @property
    def args_schema(self) -> type[BaseModel]:
        return ImageReadArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        prompt = kwargs["prompt"]
        source = kwargs["source"]
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
            obj = s3.get_object(Bucket=bucket, Key=key)
            content_length = obj.get("ContentLength", 0)
            max_size = 20 * 1024 * 1024  # 20 MB
            if content_length > max_size:
                return f"Error: image too large ({content_length / (1024 * 1024):.1f} MB, max 20 MB)."
            mime_type = obj["ContentType"]
            object_content = obj["Body"].read()
        finally:
            s3.close()
        encoded_string = base64.b64encode(object_content).decode("utf-8")
        result = await vision(prompt=prompt, mime=mime_type, data=encoded_string)
        return f"Image Result: {result}"
