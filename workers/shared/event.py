"""Parse compact Step Functions worker events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class WorkerEventError(ValueError):
    """Raised when a worker event is missing required fields."""


@dataclass(frozen=True)
class OriginalFilePointer:
    bucket: str
    key: str
    mime_type: str
    file_extension: str
    file_size_bytes: int


@dataclass(frozen=True)
class WorkerEvent:
    environment: str
    source_document_id: int
    owner_user_id: str
    original: OriginalFilePointer
    workflow_execution_arn: str | None
    workflow_execution_row_id: int | None
    attempt_number: int
    original_filename: str


@dataclass(frozen=True)
class TextExtractorEvent(WorkerEvent):
    extraction_id: int
    text_bucket: str


@dataclass(frozen=True)
class S3ObjectPointer:
    bucket: str
    key: str


@dataclass(frozen=True)
class PreviewGeneratorEvent(WorkerEvent):
    preview_id: int
    preview_bucket: str


@dataclass(frozen=True)
class CandidateExtractorEvent(WorkerEvent):
    extraction_id: int
    plain_text: S3ObjectPointer
    task_token: str | None


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkerEventError(f"{field_name} must be an object")
    return value


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerEventError(f"{field_name} must be a non-empty string")
    return value


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkerEventError(f"{field_name} must be an integer")
    return value


def parse_worker_event(event: dict[str, Any]) -> WorkerEvent:
    environment = _require_str(event.get("environment"), "environment")
    source_document_id = _require_int(event.get("sourceDocumentId"), "sourceDocumentId")
    owner_user_id = _require_str(event.get("ownerUserId"), "ownerUserId")
    original = _require_mapping(event.get("original"), "original")

    original_pointer = OriginalFilePointer(
        bucket=_require_str(original.get("bucket"), "original.bucket"),
        key=_require_str(original.get("key"), "original.key"),
        mime_type=_require_str(original.get("mimeType"), "original.mimeType"),
        file_extension=_require_str(original.get("fileExtension"), "original.fileExtension"),
        file_size_bytes=_require_int(
            original.get("fileSizeBytes"),
            "original.fileSizeBytes",
        ),
    )

    attempt_number = event.get("attemptNumber", 1)
    if attempt_number is None:
        attempt_number = 1
    if not isinstance(attempt_number, int) or attempt_number < 1:
        raise WorkerEventError("attemptNumber must be a positive integer")

    workflow_execution_arn = event.get("workflowExecutionArn")
    if workflow_execution_arn is not None and not isinstance(workflow_execution_arn, str):
        raise WorkerEventError("workflowExecutionArn must be a string when provided")

    workflow_execution_row_id = event.get("workflowExecutionRowId")
    if workflow_execution_row_id is not None and (
        isinstance(workflow_execution_row_id, bool)
        or not isinstance(workflow_execution_row_id, int)
    ):
        raise WorkerEventError("workflowExecutionRowId must be an integer when provided")

    original_filename = event.get("originalFilename")
    if original_filename is None:
        from shared.keys import filename_from_s3_key

        original_filename = filename_from_s3_key(original_pointer.key)
    elif not isinstance(original_filename, str) or not original_filename.strip():
        raise WorkerEventError("originalFilename must be a non-empty string when provided")

    return WorkerEvent(
        environment=environment,
        source_document_id=source_document_id,
        owner_user_id=owner_user_id,
        original=original_pointer,
        workflow_execution_arn=workflow_execution_arn,
        workflow_execution_row_id=workflow_execution_row_id,
        attempt_number=attempt_number,
        original_filename=original_filename,
    )


def parse_text_extractor_event(event: dict[str, Any]) -> TextExtractorEvent:
    base = parse_worker_event(event)
    extraction_id = _require_int(event.get("extractionId"), "extractionId")
    text_bucket = _require_str(event.get("textBucket"), "textBucket")
    return TextExtractorEvent(
        environment=base.environment,
        source_document_id=base.source_document_id,
        owner_user_id=base.owner_user_id,
        original=base.original,
        workflow_execution_arn=base.workflow_execution_arn,
        workflow_execution_row_id=base.workflow_execution_row_id,
        attempt_number=base.attempt_number,
        original_filename=base.original_filename,
        extraction_id=extraction_id,
        text_bucket=text_bucket,
    )


def _parse_plain_text_pointer(event: dict[str, Any]) -> S3ObjectPointer:
    package = event.get("extractedTextPackage")
    if isinstance(package, dict):
        plain_text = package.get("plainText")
        if isinstance(plain_text, dict):
            return S3ObjectPointer(
                bucket=_require_str(plain_text.get("bucket"), "extractedTextPackage.plainText.bucket"),
                key=_require_str(plain_text.get("key"), "extractedTextPackage.plainText.key"),
            )

    return S3ObjectPointer(
        bucket=_require_str(event.get("textBucket"), "textBucket"),
        key=_require_str(event.get("plainTextKey"), "plainTextKey"),
    )


def parse_candidate_extractor_event(event: dict[str, Any]) -> CandidateExtractorEvent:
    base = parse_worker_event(event)
    extraction_id = _require_int(event.get("extractionId"), "extractionId")
    plain_text = _parse_plain_text_pointer(event)

    task_token = event.get("taskToken")
    if task_token is not None and not isinstance(task_token, str):
        raise WorkerEventError("taskToken must be a string when provided")

    return CandidateExtractorEvent(
        environment=base.environment,
        source_document_id=base.source_document_id,
        owner_user_id=base.owner_user_id,
        original=base.original,
        workflow_execution_arn=base.workflow_execution_arn,
        workflow_execution_row_id=base.workflow_execution_row_id,
        attempt_number=base.attempt_number,
        original_filename=base.original_filename,
        extraction_id=extraction_id,
        plain_text=plain_text,
        task_token=task_token,
    )


def parse_preview_generator_event(event: dict[str, Any]) -> PreviewGeneratorEvent:
    base = parse_worker_event(event)
    preview_id_raw = event.get("previewId")
    if preview_id_raw is None:
        preview_id = base.attempt_number
    else:
        preview_id = _require_int(preview_id_raw, "previewId")
    preview_bucket = _require_str(event.get("previewBucket"), "previewBucket")
    return PreviewGeneratorEvent(
        environment=base.environment,
        source_document_id=base.source_document_id,
        owner_user_id=base.owner_user_id,
        original=base.original,
        workflow_execution_arn=base.workflow_execution_arn,
        workflow_execution_row_id=base.workflow_execution_row_id,
        attempt_number=base.attempt_number,
        original_filename=base.original_filename,
        preview_id=preview_id,
        preview_bucket=preview_bucket,
    )
