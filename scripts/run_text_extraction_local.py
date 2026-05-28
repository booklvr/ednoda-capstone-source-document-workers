#!/usr/bin/env python3
"""Run the text extractor locally without AWS.

This script feeds a local file into the copied text-extractor worker and writes
objects to a local directory using the same S3 key layout the worker would use.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKERS_DIR = ROOT / "workers"
TEXT_EXTRACTOR_DIR = WORKERS_DIR / "text-extractor"
for path in (WORKERS_DIR, TEXT_EXTRACTOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from handler import process_text_extraction  # noqa: E402
from shared.event import OriginalFilePointer, TextExtractorEvent  # noqa: E402


MIME_BY_EXTENSION = {
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
}


class LocalBody:
    def __init__(self, body: bytes) -> None:
        self._stream = io.BytesIO(body)

    def read(self) -> bytes:
        return self._stream.read()


class LocalS3Client:
    def __init__(
        self,
        *,
        original_bucket: str,
        original_key: str,
        original_body: bytes,
        output_dir: Path,
    ) -> None:
        self.original_bucket = original_bucket
        self.original_key = original_key
        self.original_body = original_body
        self.output_dir = output_dir

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if Bucket == self.original_bucket and Key == self.original_key:
            return {"Body": LocalBody(self.original_body)}
        raise FileNotFoundError(f"Local object not found: s3://{Bucket}/{Key}")

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes | str,
        ContentType: str | None = None,
    ) -> dict[str, Any]:
        del ContentType
        target = self.output_dir / Key
        target.parent.mkdir(parents=True, exist_ok=True)
        data = Body.encode("utf-8") if isinstance(Body, str) else Body
        target.write_bytes(data)
        return {"Bucket": Bucket, "Key": Key}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_file", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "local-output" / "text-package",
    )
    parser.add_argument("--source-document-id", type=int, default=42)
    parser.add_argument("--extraction-id", type=int, default=7)
    parser.add_argument("--attempt-number", type=int, default=1)
    parser.add_argument(
        "--owner-user-id",
        default="00000000-0000-4000-8000-000000000001",
    )
    parser.add_argument("--environment", default="dev")
    parser.add_argument("--mime-type")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_file: Path = args.input_file
    if not input_file.exists():
        raise FileNotFoundError(input_file)

    extension = input_file.suffix.lower()
    mime_type = args.mime_type or MIME_BY_EXTENSION.get(extension)
    if not mime_type:
        raise ValueError(f"Unsupported extension for local runner: {extension}")

    original_bucket = "local-source-documents"
    original_key = f"source-documents/local/original/{input_file.name}"
    text_bucket = "local-source-document-text"
    original_body = input_file.read_bytes()

    event = TextExtractorEvent(
        environment=args.environment,
        source_document_id=args.source_document_id,
        owner_user_id=args.owner_user_id,
        original=OriginalFilePointer(
            bucket=original_bucket,
            key=original_key,
            mime_type=mime_type,
            file_extension=extension,
            file_size_bytes=len(original_body),
        ),
        workflow_execution_arn=None,
        workflow_execution_row_id=None,
        attempt_number=args.attempt_number,
        original_filename=input_file.name,
        extraction_id=args.extraction_id,
        text_bucket=text_bucket,
    )

    client = LocalS3Client(
        original_bucket=original_bucket,
        original_key=original_key,
        original_body=original_body,
        output_dir=args.output_dir,
    )
    result = process_text_extraction(event, s3_client=client)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "extraction-result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nWrote local output to: {args.output_dir}")
    print(f"Result summary: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
