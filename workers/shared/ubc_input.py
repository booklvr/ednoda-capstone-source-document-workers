"""Parse and validate SourceDocumentCandidateExtractionInputV1 (UBC handoff)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from shared.contracts import CANDIDATE_EXTRACTION_ENVIRONMENTS, CANDIDATE_EXTRACTION_INPUT_VERSION
from shared.event import WorkerEventError, _require_int, _require_mapping, _require_str


@dataclass(frozen=True)
class S3ObjectPointer:
    bucket: str
    key: str


@dataclass(frozen=True)
class S3PrefixPointer:
    bucket: str
    prefix: str


@dataclass(frozen=True)
class ExtractedTextPackagePointers:
    manifest: S3ObjectPointer
    plain_text: S3ObjectPointer
    chunks_prefix: S3PrefixPointer | None
    blocks_prefix: S3PrefixPointer | None


@dataclass(frozen=True)
class OriginalUploadMetadata:
    filename: str
    mime_type: str
    file_extension: str


@dataclass(frozen=True)
class CallbackConfig:
    url: str
    signing_header: str
    task_token: str | None


@dataclass(frozen=True)
class LessonTarget:
    lesson_id: int
    default_question_list_id: int | None


@dataclass(frozen=True)
class TextbookUnitTarget:
    textbook_id: int
    textbook_unit_id: int


@dataclass(frozen=True)
class UbcCandidateExtractionInputV1:
    environment: str
    source_document_id: int
    extraction_id: int
    target_type: str
    lesson_target: LessonTarget | None
    textbook_unit_target: TextbookUnitTarget | None
    extracted_text_package: ExtractedTextPackagePointers
    original: OriginalUploadMetadata
    callback: CallbackConfig


def _parse_s3_pointer(value: Any, field_name: str) -> S3ObjectPointer:
    mapping = _require_mapping(value, field_name)
    return S3ObjectPointer(
        bucket=_require_str(mapping.get("bucket"), f"{field_name}.bucket"),
        key=_require_str(mapping.get("key"), f"{field_name}.key"),
    )


def _parse_optional_prefix_pointer(
    value: Any,
    field_name: str,
) -> S3PrefixPointer | None:
    if value is None:
        return None
    mapping = _require_mapping(value, field_name)
    return S3PrefixPointer(
        bucket=_require_str(mapping.get("bucket"), f"{field_name}.bucket"),
        prefix=_require_str(mapping.get("prefix"), f"{field_name}.prefix"),
    )


def _parse_target(event: dict[str, Any]) -> tuple[str, LessonTarget | None, TextbookUnitTarget | None]:
    target = _require_mapping(event.get("target"), "target")
    target_type = _require_str(target.get("targetType"), "target.targetType")

    if target_type == "lesson":
        lesson_id = _require_int(target.get("lessonId"), "target.lessonId")
        default_question_list_id = target.get("defaultQuestionListId")
        if default_question_list_id is not None:
            default_question_list_id = _require_int(
                default_question_list_id,
                "target.defaultQuestionListId",
            )
        return (
            target_type,
            LessonTarget(
                lesson_id=lesson_id,
                default_question_list_id=default_question_list_id,
            ),
            None,
        )

    if target_type == "textbook_unit":
        return (
            target_type,
            None,
            TextbookUnitTarget(
                textbook_id=_require_int(target.get("textbookId"), "target.textbookId"),
                textbook_unit_id=_require_int(
                    target.get("textbookUnitId"),
                    "target.textbookUnitId",
                ),
            ),
        )

    raise WorkerEventError(f"target.targetType is unsupported: {target_type}")


def _parse_callback(event: dict[str, Any]) -> CallbackConfig:
    callback = _require_mapping(event.get("callback"), "callback")
    url = _require_str(callback.get("url"), "callback.url")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WorkerEventError("callback.url must be a valid http(s) URL")

    signing_header = _require_str(callback.get("signingHeader"), "callback.signingHeader")
    if signing_header != "X-Ednoda-Signature":
        raise WorkerEventError("callback.signingHeader must be X-Ednoda-Signature")

    task_token = callback.get("taskToken")
    if task_token is not None and not isinstance(task_token, str):
        raise WorkerEventError("callback.taskToken must be a string when provided")

    return CallbackConfig(url=url, signing_header=signing_header, task_token=task_token)


def parse_ubc_candidate_extraction_input_v1(event: dict[str, Any]) -> UbcCandidateExtractionInputV1:
    if not isinstance(event, dict):
        raise WorkerEventError("handoff payload must be an object")

    version = _require_str(event.get("version"), "version")
    if version != CANDIDATE_EXTRACTION_INPUT_VERSION:
        raise WorkerEventError(
            f"version must be {CANDIDATE_EXTRACTION_INPUT_VERSION}",
        )

    environment = _require_str(event.get("environment"), "environment")
    if environment not in CANDIDATE_EXTRACTION_ENVIRONMENTS:
        raise WorkerEventError("environment must be dev, staging, demo, or prod")

    package_mapping = _require_mapping(event.get("extractedTextPackage"), "extractedTextPackage")
    original_mapping = _require_mapping(event.get("original"), "original")
    target_type, lesson_target, textbook_unit_target = _parse_target(event)

    return UbcCandidateExtractionInputV1(
        environment=environment,
        source_document_id=_require_int(event.get("sourceDocumentId"), "sourceDocumentId"),
        extraction_id=_require_int(event.get("extractionId"), "extractionId"),
        target_type=target_type,
        lesson_target=lesson_target,
        textbook_unit_target=textbook_unit_target,
        extracted_text_package=ExtractedTextPackagePointers(
            manifest=_parse_s3_pointer(package_mapping.get("manifest"), "extractedTextPackage.manifest"),
            plain_text=_parse_s3_pointer(
                package_mapping.get("plainText"),
                "extractedTextPackage.plainText",
            ),
            chunks_prefix=_parse_optional_prefix_pointer(
                package_mapping.get("chunksPrefix"),
                "extractedTextPackage.chunksPrefix",
            ),
            blocks_prefix=_parse_optional_prefix_pointer(
                package_mapping.get("blocksPrefix"),
                "extractedTextPackage.blocksPrefix",
            ),
        ),
        original=OriginalUploadMetadata(
            filename=_require_str(original_mapping.get("filename"), "original.filename"),
            mime_type=_require_str(original_mapping.get("mimeType"), "original.mimeType"),
            file_extension=_require_str(
                original_mapping.get("fileExtension"),
                "original.fileExtension",
            ),
        ),
        callback=_parse_callback(event),
    )
