"""Unit tests for Alpha text extraction logic."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WORKER_ROOT = Path(__file__).resolve().parents[2]
TEXT_EXTRACTOR_DIR = WORKER_ROOT / "text-extractor"
for path in (WORKER_ROOT, TEXT_EXTRACTOR_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared.contracts import (  # noqa: E402
    EXTRACTION_STATUS_OCR_REQUIRED,
    EXTRACTION_STATUS_READY,
    MANIFEST_VERSION,
    WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD,
)
from shared.keys import build_extraction_text_package_keys  # noqa: E402
from package_writer import build_manifest, is_pdf_file, is_txt_file  # noqa: E402
from pdf_logic import PdfPageText, assess_pdf_text_coverage, build_pdf_extraction  # noqa: E402
from txt_logic import build_txt_extraction, split_paragraph_blocks  # noqa: E402


class TxtLogicTests(unittest.TestCase):
    def test_split_paragraph_blocks(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird."
        self.assertEqual(
            split_paragraph_blocks(text),
            ["First paragraph.", "Second paragraph.", "Third."],
        )

    def test_build_txt_extraction_creates_blocks_and_chunks(self) -> None:
        raw = b"Alpha lesson notes.\n\nSecond paragraph with more text."
        result = build_txt_extraction(raw)
        self.assertEqual(result.plain_text.count("\n\n"), 1)
        self.assertEqual(len(result.blocks), 2)
        self.assertGreaterEqual(len(result.chunks), 1)
        self.assertEqual(result.blocks[0].block_id, "block-000001")

    def test_build_txt_extraction_applies_conservative_format_cleanup(self) -> None:
        raw = "Slide 2\n• photo-\nsynthesis\n\nDefinition text.".encode("utf-8")

        result = build_txt_extraction(raw)

        self.assertIn("Slide 2", result.plain_text)
        self.assertIn("- photo-", result.plain_text)
        self.assertIn("synthesis", result.plain_text)
        self.assertEqual(result.detected_languages, [])

    def test_build_txt_extraction_preserves_numbered_and_bilingual_lines(self) -> None:
        raw = "1\napple\n2\nbanana\n안녕하세요\nHello".encode("utf-8")

        result = build_txt_extraction(raw)

        self.assertIn("1", result.plain_text)
        self.assertIn("2", result.plain_text)
        self.assertIn("안녕하세요", result.plain_text)
        self.assertEqual(result.detected_languages, [])


class PdfLogicTests(unittest.TestCase):
    def test_assess_pdf_text_coverage_requires_meaningful_text(self) -> None:
        pages = [
            PdfPageText(page_number=1, text=""),
            PdfPageText(page_number=2, text=""),
            PdfPageText(page_number=3, text=""),
            PdfPageText(page_number=4, text=""),
        ]
        ok, warnings = assess_pdf_text_coverage(pages)
        self.assertFalse(ok)
        self.assertEqual(warnings, [WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD])

    def test_build_pdf_extraction_marks_ocr_required_for_scanned_pdf(self) -> None:
        import pdf_logic

        original = pdf_logic.extract_pdf_page_texts
        pdf_logic.extract_pdf_page_texts = lambda _raw: [
            PdfPageText(page_number=1, text=""),
            PdfPageText(page_number=2, text=""),
        ]
        try:
            result = build_pdf_extraction(b"%PDF-1.4")
            self.assertEqual(result.status, EXTRACTION_STATUS_OCR_REQUIRED)
            self.assertEqual(result.page_count, 2)
        finally:
            pdf_logic.extract_pdf_page_texts = original

    def test_build_pdf_extraction_ready_when_coverage_is_sufficient(self) -> None:
        import pdf_logic

        original = pdf_logic.extract_pdf_page_texts
        pdf_logic.extract_pdf_page_texts = lambda _raw: [
            PdfPageText(page_number=1, text="Embedded lesson vocabulary for Alpha tests."),
            PdfPageText(page_number=2, text="Additional embedded text on page two."),
        ]
        try:
            result = build_pdf_extraction(b"%PDF-1.4")
            self.assertEqual(result.status, EXTRACTION_STATUS_READY)
            self.assertEqual(len(result.blocks), 2)
            self.assertEqual(result.blocks[0].source_page_number, 1)
            self.assertEqual(result.blocks[1].source_page_number, 2)
            self.assertGreater(result.plain_text, "")
        finally:
            pdf_logic.extract_pdf_page_texts = original

    def test_build_pdf_extraction_preserves_source_page_number_when_pages_are_sparse(
        self,
    ) -> None:
        import pdf_logic

        original = pdf_logic.extract_pdf_page_texts
        pdf_logic.extract_pdf_page_texts = lambda _raw: [
            PdfPageText(page_number=1, text=""),
            PdfPageText(page_number=2, text=""),
            PdfPageText(page_number=3, text=""),
            PdfPageText(
                page_number=4,
                text="Embedded lesson vocabulary on page four for Alpha tests.",
            ),
        ]
        try:
            result = build_pdf_extraction(b"%PDF-1.4")
            self.assertEqual(result.status, EXTRACTION_STATUS_READY)
            self.assertEqual(len(result.blocks), 1)
            self.assertEqual(result.blocks[0].source_page_number, 4)
            self.assertEqual(result.blocks[0].block_id, "block-000004")
        finally:
            pdf_logic.extract_pdf_page_texts = original

    def test_pdf_manifest_uses_source_page_number_not_block_index(self) -> None:
        import pdf_logic

        original = pdf_logic.extract_pdf_page_texts
        pdf_logic.extract_pdf_page_texts = lambda _raw: [
            PdfPageText(page_number=1, text=""),
            PdfPageText(page_number=2, text=""),
            PdfPageText(page_number=3, text=""),
            PdfPageText(
                page_number=4,
                text="Embedded lesson vocabulary on page four for Alpha tests.",
            ),
        ]
        try:
            extracted = build_pdf_extraction(b"%PDF-1.4")
            package_keys = build_extraction_text_package_keys(
                "ednoda-dev-source-document-text",
                "00000000-0000-4000-8000-000000000001",
                42,
                7,
            )
            manifest = build_manifest(
                source_document_id=42,
                extraction_id=7,
                original_filename="lesson.pdf",
                original_mime_type="application/pdf",
                file_extension=".pdf",
                original_bucket="ednoda-dev-source-documents",
                original_key="source-documents/user/u/document/42/original/lesson.pdf",
                text_bucket="ednoda-dev-source-document-text",
                package_keys=package_keys,
                extraction_strategy="pdf_text_layer",
                status=EXTRACTION_STATUS_READY,
                plain_text=extracted.plain_text,
                blocks=extracted.blocks,
                chunks=extracted.chunks,
                page_count=extracted.page_count,
                detected_languages=extracted.detected_languages,
                warnings=extracted.warnings,
            )
            self.assertEqual(manifest["outputs"]["blockIndex"][0]["sourcePageNumber"], 4)
        finally:
            pdf_logic.extract_pdf_page_texts = original

    def test_build_pdf_extraction_preserves_repeated_lesson_lines(self) -> None:
        import pdf_logic

        original = pdf_logic.extract_pdf_page_texts
        pdf_logic.extract_pdf_page_texts = lambda _raw: [
            PdfPageText(
                page_number=1,
                text="Repeat after me.\nPhotosynthesis vocabulary text for Alpha tests.",
            ),
            PdfPageText(
                page_number=2,
                text="Repeat after me.\nChlorophyll vocabulary text for Alpha tests.",
            ),
            PdfPageText(
                page_number=3,
                text="Repeat after me.\nPlant cells vocabulary text for Alpha tests.",
            ),
        ]
        try:
            result = build_pdf_extraction(b"%PDF-1.4")
            self.assertEqual(result.status, EXTRACTION_STATUS_READY)
            self.assertEqual(result.plain_text.count("Repeat after me."), 3)
            self.assertIn("Photosynthesis vocabulary", result.plain_text)
        finally:
            pdf_logic.extract_pdf_page_texts = original

    def test_build_pdf_extraction_returns_partial_for_mixed_text_layer(self) -> None:
        import pdf_logic

        original = pdf_logic.extract_pdf_page_texts
        pdf_logic.extract_pdf_page_texts = lambda _raw: [
            PdfPageText(page_number=1, text=""),
            PdfPageText(page_number=2, text=""),
            PdfPageText(page_number=3, text=""),
            PdfPageText(
                page_number=4,
                text="Useful embedded lesson vocabulary on page four for Alpha tests.",
            ),
            PdfPageText(page_number=5, text=""),
            PdfPageText(page_number=6, text=""),
            PdfPageText(page_number=7, text=""),
            PdfPageText(page_number=8, text=""),
        ]
        try:
            result = build_pdf_extraction(b"%PDF-1.4")
            self.assertEqual(result.status, "partial")
            self.assertEqual(len(result.blocks), 1)
            self.assertEqual(result.blocks[0].source_page_number, 4)
            self.assertIn(WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD, result.warnings)
        finally:
            pdf_logic.extract_pdf_page_texts = original


class PackageWriterTests(unittest.TestCase):
    def test_manifest_shape_for_ready_txt(self) -> None:
        raw = b"Hello lesson.\n\nSecond paragraph."
        extracted = build_txt_extraction(raw)
        package_keys = build_extraction_text_package_keys(
            "ednoda-dev-source-document-text",
            "00000000-0000-4000-8000-000000000001",
            42,
            7,
        )
        manifest = build_manifest(
            source_document_id=42,
            extraction_id=7,
            original_filename="lesson.txt",
            original_mime_type="text/plain",
            file_extension=".txt",
            original_bucket="ednoda-dev-source-documents",
            original_key="source-documents/user/u/document/42/original/lesson.txt",
            text_bucket="ednoda-dev-source-document-text",
            package_keys=package_keys,
            extraction_strategy="plain_text",
            status=EXTRACTION_STATUS_READY,
            plain_text=extracted.plain_text,
            blocks=extracted.blocks,
            chunks=extracted.chunks,
            page_count=None,
            detected_languages=["en"],
            warnings=[],
        )
        self.assertEqual(manifest["version"], MANIFEST_VERSION)
        self.assertEqual(manifest["document"]["extractionId"], 7)
        self.assertEqual(manifest["outputs"]["plainText"]["key"], package_keys["plainTextKey"])


class TextExtractorHandlerTests(unittest.TestCase):
    def test_handler_processes_txt_and_writes_manifest_last(self) -> None:
        import handler as text_handler

        writes: list[tuple[str, str]] = []

        class FakeBody:
            def __init__(self, data: bytes) -> None:
                self._data = data

            def read(self) -> bytes:
                return self._data

        class FakeS3:
            def get_object(self, *, Bucket: str, Key: str) -> dict:
                return {"Body": FakeBody(b"Lesson one.\n\nLesson two.")}

            def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, ContentType=None) -> dict:
                body = Body.encode("utf-8") if isinstance(Body, str) else Body
                writes.append((Key, body.decode("utf-8") if Key.endswith(".json") or Key.endswith(".txt") else "binary"))
                return {}

        event = {
            "environment": "dev",
            "sourceDocumentId": 42,
            "ownerUserId": "00000000-0000-4000-8000-000000000001",
            "extractionId": 7,
            "textBucket": "ednoda-dev-source-document-text",
            "attemptNumber": 1,
            "originalFilename": "lesson.txt",
            "original": {
                "bucket": "ednoda-dev-source-documents",
                "key": "source-documents/user/u/document/42/original/lesson.txt",
                "mimeType": "text/plain",
                "fileExtension": ".txt",
                "fileSizeBytes": 32,
            },
        }

        result = text_handler.process_text_extraction(
            text_handler.parse_text_extractor_event(event),
            s3_client=FakeS3(),
        )

        self.assertEqual(result["status"], EXTRACTION_STATUS_READY)
        self.assertTrue(result["textAvailable"])
        self.assertEqual(result["textBucket"], "ednoda-dev-source-document-text")
        self.assertEqual(result["blockCount"], 2)
        self.assertEqual(writes[-1][0].endswith("manifest.json"), True)

        manifest = json.loads(writes[-1][1])
        self.assertEqual(manifest["extraction"]["status"], EXTRACTION_STATUS_READY)

    def test_file_type_helpers(self) -> None:
        self.assertTrue(is_txt_file(".txt", "text/plain"))
        self.assertTrue(is_pdf_file(".pdf", "application/pdf"))

    def test_handler_returns_failed_for_document_processing_errors(self) -> None:
        import handler as text_handler

        event = {
            "environment": "dev",
            "sourceDocumentId": 42,
            "ownerUserId": "00000000-0000-4000-8000-000000000001",
            "extractionId": 7,
            "textBucket": "ednoda-dev-source-document-text",
            "attemptNumber": 1,
            "originalFilename": "lesson.txt",
            "original": {
                "bucket": "ednoda-dev-source-documents",
                "key": "source-documents/user/u/document/42/original/lesson.txt",
                "mimeType": "text/plain",
                "fileExtension": ".txt",
                "fileSizeBytes": 32,
            },
        }

        with patch.object(
            text_handler,
            "process_text_extraction",
            side_effect=ValueError("corrupt document"),
        ):
            result = text_handler.handler(event)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["code"], "text_extraction_failed")

    def test_handler_reraises_transient_s3_errors(self) -> None:
        import handler as text_handler
        from botocore.exceptions import ClientError

        event = {
            "environment": "dev",
            "sourceDocumentId": 42,
            "ownerUserId": "00000000-0000-4000-8000-000000000001",
            "extractionId": 7,
            "textBucket": "ednoda-dev-source-document-text",
            "attemptNumber": 1,
            "originalFilename": "lesson.txt",
            "original": {
                "bucket": "ednoda-dev-source-documents",
                "key": "source-documents/user/u/document/42/original/lesson.txt",
                "mimeType": "text/plain",
                "fileExtension": ".txt",
                "fileSizeBytes": 32,
            },
        }
        transient_error = ClientError(
            {
                "Error": {"Code": "SlowDown", "Message": "reduce request rate"},
                "ResponseMetadata": {"HTTPStatusCode": 503},
            },
            "GetObject",
        )

        with patch.object(
            text_handler,
            "process_text_extraction",
            side_effect=transient_error,
        ):
            with self.assertRaises(ClientError):
                text_handler.handler(event)


if __name__ == "__main__":
    unittest.main()
