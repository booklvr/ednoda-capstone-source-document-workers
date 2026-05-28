"""Backend file sniffing after malware gate and before worker parsing."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass

from shared.file_types import (
    is_csv_file,
    is_docx_file,
    is_pdf_file,
    is_pptx_file,
    is_txt_file,
    normalize_extension,
)


@dataclass(frozen=True)
class FileSniffResult:
    valid: bool
    error_code: str | None = None
    message: str | None = None


def _has_pdf_signature(raw: bytes) -> bool:
    return raw.startswith(b"%PDF-")


def _has_zip_signature(raw: bytes) -> bool:
    return len(raw) >= 4 and raw[0:4] == b"PK\x03\x04"


def _is_text_like(raw: bytes) -> bool:
    if not raw:
        return False

    offset = 0
    if raw.startswith(b"\xef\xbb\xbf"):
        offset = 3

    for byte in raw[offset:]:
        if byte == 0:
            return False
        if byte < 0x20 and byte not in (0x09, 0x0A, 0x0D):
            return False
        if byte == 0x7F:
            return False
    return True


def _csv_parses(raw: bytes) -> bool:
    if not _is_text_like(raw):
        return False

    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        try:
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
        except csv.Error:
            return False
        return len(rows) > 0

    return False


def _zip_contains_office_parts(raw: bytes, *, family: str) -> bool:
    if not _has_zip_signature(raw):
        return False

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return False

    if "[Content_Types].xml" not in names:
        return False

    if family == "docx":
        return any(name.startswith("word/") for name in names)
    if family == "pptx":
        return any(name.startswith("ppt/") for name in names)
    return False


def validate_source_document_file_content(
    raw: bytes,
    *,
    file_extension: str,
    mime_type: str,
) -> FileSniffResult:
    extension = normalize_extension(file_extension)

    if is_pdf_file(file_extension, mime_type):
        if not _has_pdf_signature(raw):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="File content does not match declared PDF type.",
            )
        return FileSniffResult(valid=True)

    if is_docx_file(file_extension, mime_type):
        if not _zip_contains_office_parts(raw, family="docx"):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="File content does not match declared DOCX type.",
            )
        return FileSniffResult(valid=True)

    if is_pptx_file(file_extension, mime_type):
        if not _zip_contains_office_parts(raw, family="pptx"):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="File content does not match declared PPTX type.",
            )
        return FileSniffResult(valid=True)

    if is_csv_file(file_extension, mime_type):
        if _has_pdf_signature(raw) or _has_zip_signature(raw):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="CSV content looks like a binary or office file.",
            )
        if not _csv_parses(raw):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="File content does not parse as CSV.",
            )
        return FileSniffResult(valid=True)

    if is_txt_file(file_extension, mime_type):
        if _has_pdf_signature(raw) or _has_zip_signature(raw):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="Text content looks like a binary or office file.",
            )
        if not _is_text_like(raw):
            return FileSniffResult(
                valid=False,
                error_code="signature_mismatch",
                message="File content does not look like plain text.",
            )
        return FileSniffResult(valid=True)

    return FileSniffResult(
        valid=False,
        error_code="unsupported_extension",
        message=f"Unsupported file extension for sniffing ({extension}).",
    )
