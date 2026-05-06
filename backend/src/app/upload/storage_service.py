import uuid

import boto3
from botocore.client import Config
from pydantic import BaseModel

from app.config import settings


class UploadRequest(BaseModel):
    file_name: str
    file_type: str


def get_upload_url(req: UploadRequest):
    key = f"{uuid.uuid4()}-{req.file_name}"
    s3 = boto3.client(
        "s3",
        endpoint_url=settings.external_s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.region_name,
        config=Config(signature_version="s3v4"),
    )
    url = s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": settings.bucket_name,
            "Key": key,
            "ContentType": req.file_type,
        },
        ExpiresIn=60,
    )

    return {"url": url, "key": key}
