"""Minimal S3 helpers for worker handlers (boto3 imported lazily)."""

from __future__ import annotations

from typing import Protocol


class S3Client(Protocol):
    def get_object(self, *, Bucket: str, Key: str) -> dict: ...

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes | str,
        ContentType: str | None = None,
    ) -> dict: ...


def create_boto3_s3_client():
    import boto3

    return boto3.client("s3")


def read_object_bytes(client: S3Client, *, bucket: str, key: str) -> bytes:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    if isinstance(body, str):
        return body.encode("utf-8")
    return body


def write_object_bytes(
    client: S3Client,
    *,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str | None = None,
) -> None:
    kwargs: dict[str, object] = {
        "Bucket": bucket,
        "Key": key,
        "Body": body,
    }
    if content_type:
        kwargs["ContentType"] = content_type
    client.put_object(**kwargs)
