"""Unit tests for signed preview callback posting."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

WORKER_ROOT = Path(__file__).resolve().parents[2]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from shared.callback_post import (  # noqa: E402
    build_extraction_callback_body,
    build_node_candidates_callback_body,
    build_preview_callback_body,
    post_extraction_callback,
    post_node_candidates_callback,
    post_preview_callback,
    resolve_node_candidates_callback_url,
    sign_callback_body,
)
from shared.contracts import (  # noqa: E402
    EXTRACTION_STATUS_OCR_REQUIRED,
    EXTRACTION_STATUS_READY,
    PREVIEW_STATUS_READY,
    PREVIEW_STRATEGY_PAGE_IMAGES,
    PREVIEW_STRATEGY_PLAIN_TEXT,
    WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD,
)
from shared.event import (  # noqa: E402
    CandidateExtractorEvent,
    OriginalFilePointer,
    PreviewGeneratorEvent,
    S3ObjectPointer,
    TextExtractorEvent,
)


def load_preview_handler_module():
    preview_dir = WORKER_ROOT / "preview-image-generator"
    spec = importlib.util.spec_from_file_location(
        "preview_worker_handler_for_callback_tests",
        preview_dir / "handler.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_text_extractor_handler_module():
    text_extractor_dir = WORKER_ROOT / "text-extractor"
    spec = importlib.util.spec_from_file_location(
        "text_extractor_handler_for_callback_tests",
        text_extractor_dir / "handler.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PreviewCallbackPostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = PreviewGeneratorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/lesson.txt",
                mime_type="text/plain",
                file_extension=".txt",
                file_size_bytes=32,
            ),
            workflow_execution_arn="arn:aws:states:us-west-2:123:execution:test",
            workflow_execution_row_id=9,
            attempt_number=1,
            original_filename="lesson.txt",
            preview_id=1,
            preview_bucket="ednoda-dev-source-document-previews",
        )
        self.result = {
            "status": PREVIEW_STATUS_READY,
            "branch": "preview",
            "previewBucket": "ednoda-dev-source-document-previews",
            "previewPrefix": (
                "source-document-previews/user/u/document/42/preview/1/"
            ),
        }

    def test_build_preview_callback_body_matches_alpha_schema(self) -> None:
        body = build_preview_callback_body(self.event, self.result)

        self.assertEqual(body["sourceDocumentId"], 42)
        self.assertEqual(body["attemptNumber"], 1)
        self.assertEqual(body["previewId"], 1)
        self.assertEqual(body["status"], PREVIEW_STATUS_READY)
        self.assertEqual(body["previewStrategy"], PREVIEW_STRATEGY_PLAIN_TEXT)
        self.assertEqual(body["previewBucket"], self.result["previewBucket"])
        self.assertEqual(body["previewPrefix"], self.result["previewPrefix"])
        self.assertIn("occurredAtIso", body)
        self.assertNotIn("pages", body)
        self.assertNotIn("secret", json.dumps(body))

    def test_build_preview_callback_body_includes_pdf_page_rows(self) -> None:
        pdf_event = PreviewGeneratorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/lesson.pdf",
                mime_type="application/pdf",
                file_extension=".pdf",
                file_size_bytes=128,
            ),
            workflow_execution_arn="arn:aws:states:us-west-2:123:execution:test",
            workflow_execution_row_id=9,
            attempt_number=1,
            original_filename="lesson.pdf",
            preview_id=1,
            preview_bucket="ednoda-dev-source-document-previews",
        )
        preview_prefix = (
            "source-document-previews/user/u/document/42/preview/1/"
        )
        pages = [
            {
                "pageNumber": 1,
                "imageKey": f"{preview_prefix}pages/page-000001.webp",
                "width": 800,
                "height": 1100,
            },
            {
                "pageNumber": 2,
                "imageKey": f"{preview_prefix}pages/page-000002.webp",
                "width": 800,
                "height": 1100,
            },
        ]
        pdf_result = {
            "status": PREVIEW_STATUS_READY,
            "branch": "preview",
            "previewBucket": "ednoda-dev-source-document-previews",
            "previewPrefix": preview_prefix,
            "pageCount": 2,
            "pages": pages,
        }

        body = build_preview_callback_body(pdf_event, pdf_result)

        self.assertEqual(body["previewStrategy"], PREVIEW_STRATEGY_PAGE_IMAGES)
        self.assertEqual(body["pageCount"], 2)
        self.assertEqual(body["pages"], pages)

    def test_build_preview_callback_body_uses_page_images_for_pptx(self) -> None:
        pptx_event = PreviewGeneratorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/slides.pptx",
                mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                file_extension=".pptx",
                file_size_bytes=1024,
            ),
            workflow_execution_arn="arn:aws:states:us-west-2:123:execution:test",
            workflow_execution_row_id=9,
            attempt_number=1,
            original_filename="slides.pptx",
            preview_id=1,
            preview_bucket="ednoda-dev-source-document-previews",
        )
        preview_prefix = (
            "source-document-previews/user/u/document/42/preview/1/"
        )
        pptx_result = {
            "status": PREVIEW_STATUS_READY,
            "branch": "preview",
            "previewBucket": "ednoda-dev-source-document-previews",
            "previewPrefix": preview_prefix,
            "pageCount": 1,
            "pages": [
                {
                    "pageNumber": 1,
                    "imageKey": f"{preview_prefix}pages/page-000001.webp",
                    "width": 1280,
                    "height": 720,
                },
            ],
        }

        body = build_preview_callback_body(pptx_event, pptx_result)

        self.assertEqual(body["previewStrategy"], PREVIEW_STRATEGY_PAGE_IMAGES)
        self.assertEqual(body["pageCount"], 1)
        self.assertEqual(len(body["pages"]), 1)

    def test_build_preview_callback_body_uses_page_images_for_docx(self) -> None:
        docx_event = PreviewGeneratorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/lesson.docx",
                mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                file_extension=".docx",
                file_size_bytes=1024,
            ),
            workflow_execution_arn="arn:aws:states:us-west-2:123:execution:test",
            workflow_execution_row_id=9,
            attempt_number=1,
            original_filename="lesson.docx",
            preview_id=1,
            preview_bucket="ednoda-dev-source-document-previews",
        )
        preview_prefix = (
            "source-document-previews/user/u/document/42/preview/1/"
        )
        docx_result = {
            "status": PREVIEW_STATUS_READY,
            "branch": "preview",
            "previewBucket": "ednoda-dev-source-document-previews",
            "previewPrefix": preview_prefix,
            "pageCount": 1,
            "pages": [
                {
                    "pageNumber": 1,
                    "imageKey": f"{preview_prefix}pages/page-000001.webp",
                    "width": 816,
                    "height": 1056,
                },
            ],
        }

        body = build_preview_callback_body(docx_event, docx_result)

        self.assertEqual(body["previewStrategy"], PREVIEW_STRATEGY_PAGE_IMAGES)
        self.assertEqual(body["pageCount"], 1)
        self.assertEqual(len(body["pages"]), 1)

    def test_sign_callback_body_is_hmac_sha256_hex(self) -> None:
        raw_body = json.dumps({"sourceDocumentId": 42}, separators=(",", ":"))
        signature = sign_callback_body("test-secret", raw_body)
        self.assertEqual(len(signature), 64)
        self.assertNotIn("test-secret", signature)

    @patch("shared.callback_post.httpx.post")
    def test_post_preview_callback_sends_signature_header(self, post_mock) -> None:
        captured: dict[str, object] = {}

        def capture_request(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            content = kwargs["content"]
            captured["body"] = (
                content.decode("utf-8") if isinstance(content, bytes) else content
            )
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
            )

        post_mock.side_effect = capture_request

        with patch.dict(
            "os.environ",
            {
                "EDNODA_CALLBACK_BASE_URL": "https://nick-dev.ednoda.com",
                "SOURCE_DOCUMENT_CALLBACK_SECRET": "test-secret",
            },
            clear=False,
        ):
            post_preview_callback(
                {
                    "sourceDocumentId": 42,
                    "attemptNumber": 1,
                    "status": PREVIEW_STATUS_READY,
                    "previewStrategy": PREVIEW_STRATEGY_PLAIN_TEXT,
                    "previewBucket": "bucket",
                    "previewPrefix": "prefix/",
                },
            )

        headers = captured["headers"]
        self.assertIn("X-Ednoda-Signature", headers)
        self.assertEqual(headers["User-Agent"], "EdnodaSourceDocumentWorker/1.0")
        self.assertNotIn("test-secret", str(headers))
        self.assertNotIn("test-secret", captured["body"])
        self.assertTrue(
            str(captured["url"]).endswith("/api/source-documents/preview/callback"),
        )

    @patch("shared.callback_post.try_post_preview_callback")
    def test_handler_posts_callback_after_txt_preview(self, callback_mock) -> None:
        preview_handler = load_preview_handler_module()

        event = {
            "environment": "dev",
            "sourceDocumentId": 42,
            "ownerUserId": "00000000-0000-4000-8000-000000000001",
            "previewId": 5,
            "previewBucket": "ednoda-dev-source-document-previews",
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

        ready_result = {
            "status": PREVIEW_STATUS_READY,
            "branch": "preview",
            "previewBucket": "ednoda-dev-source-document-previews",
            "previewPrefix": (
                "source-document-previews/user/u/document/42/preview/5/"
            ),
        }

        with patch.object(
            preview_handler,
            "process_preview_generation",
            return_value=ready_result,
        ):
            result = preview_handler.handler(event)

        self.assertEqual(result["status"], PREVIEW_STATUS_READY)
        callback_mock.assert_called_once()
        callback_body = callback_mock.call_args.args[0]
        self.assertEqual(callback_body["status"], PREVIEW_STATUS_READY)
        self.assertEqual(callback_body["previewStrategy"], PREVIEW_STRATEGY_PLAIN_TEXT)
        self.assertNotIn("pages", callback_body)

    @patch("shared.callback_post.try_post_preview_callback")
    def test_handler_posts_callback_after_pdf_preview(self, callback_mock) -> None:
        preview_handler = load_preview_handler_module()

        preview_prefix = (
            "source-document-previews/user/u/document/42/preview/5/"
        )
        pages = [
            {
                "pageNumber": 1,
                "imageKey": f"{preview_prefix}pages/page-000001.webp",
                "width": 800,
                "height": 1100,
            },
        ]
        event = {
            "environment": "dev",
            "sourceDocumentId": 42,
            "ownerUserId": "00000000-0000-4000-8000-000000000001",
            "previewId": 5,
            "previewBucket": "ednoda-dev-source-document-previews",
            "attemptNumber": 1,
            "originalFilename": "lesson.pdf",
            "original": {
                "bucket": "ednoda-dev-source-documents",
                "key": "source-documents/user/u/document/42/original/lesson.pdf",
                "mimeType": "application/pdf",
                "fileExtension": ".pdf",
                "fileSizeBytes": 128,
            },
        }
        ready_result = {
            "status": PREVIEW_STATUS_READY,
            "branch": "preview",
            "previewBucket": "ednoda-dev-source-document-previews",
            "previewPrefix": preview_prefix,
            "pageCount": 1,
            "pages": pages,
        }

        with patch.object(
            preview_handler,
            "process_preview_generation",
            return_value=ready_result,
        ):
            result = preview_handler.handler(event)

        self.assertEqual(result["status"], PREVIEW_STATUS_READY)
        callback_mock.assert_called_once()
        callback_body = callback_mock.call_args.args[0]
        self.assertEqual(callback_body["previewStrategy"], PREVIEW_STRATEGY_PAGE_IMAGES)
        self.assertEqual(callback_body["pages"], pages)

    @patch("shared.callback_post.httpx.post")
    def test_post_preview_callback_raises_on_http_error(self, post_mock) -> None:
        post_mock.return_value = httpx.Response(
            400,
            text="Bad Request",
            request=httpx.Request(
                "POST",
                "https://nick-dev.ednoda.com/api/source-documents/preview/callback",
            ),
        )

        with patch.dict(
            "os.environ",
            {
                "EDNODA_CALLBACK_BASE_URL": "https://nick-dev.ednoda.com",
                "SOURCE_DOCUMENT_CALLBACK_SECRET": "test-secret",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                post_preview_callback(
                    {
                        "sourceDocumentId": 42,
                        "attemptNumber": 1,
                        "status": "failed",
                        "previewStrategy": "unsupported",
                        "error": {"code": "unsupported_file_type", "message": "nope"},
                    },
                )


class ExtractionCallbackPostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = TextExtractorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/lesson.txt",
                mime_type="text/plain",
                file_extension=".txt",
                file_size_bytes=32,
            ),
            workflow_execution_arn="arn:aws:states:us-west-2:123:execution:test",
            workflow_execution_row_id=9,
            attempt_number=1,
            original_filename="lesson.txt",
            extraction_id=7,
            text_bucket="ednoda-dev-source-document-text",
        )
        self.ready_result = {
            "status": EXTRACTION_STATUS_READY,
            "branch": "extraction",
            "textAvailable": True,
            "textBucket": "ednoda-dev-source-document-text",
            "manifestKey": (
                "source-document-text/user/u/document/42/extraction/7/manifest.json"
            ),
            "plainTextKey": (
                "source-document-text/user/u/document/42/extraction/7/plain.txt"
            ),
            "charCount": 120,
            "blockCount": 2,
            "chunkCount": 1,
        }

    def test_build_extraction_callback_body_matches_alpha_schema(self) -> None:
        body = build_extraction_callback_body(self.event, self.ready_result)

        self.assertEqual(body["sourceDocumentId"], 42)
        self.assertEqual(body["attemptNumber"], 1)
        self.assertEqual(body["extractionId"], 7)
        self.assertEqual(body["status"], EXTRACTION_STATUS_READY)
        self.assertEqual(body["extractionStrategy"], PREVIEW_STRATEGY_PLAIN_TEXT)
        self.assertEqual(body["textBucket"], self.ready_result["textBucket"])
        self.assertEqual(body["manifestKey"], self.ready_result["manifestKey"])
        self.assertEqual(body["plainTextKey"], self.ready_result["plainTextKey"])
        self.assertEqual(body["charCount"], 120)
        self.assertEqual(body["blockCount"], 2)
        self.assertEqual(body["chunkCount"], 1)
        self.assertIn("occurredAtIso", body)
        self.assertNotIn("plainText", body)
        self.assertNotIn("blocks", body)
        self.assertNotIn("chunks", body)

    def test_build_extraction_callback_body_omits_pointers_for_ocr_required(self) -> None:
        body = build_extraction_callback_body(
            self.event,
            {
                "status": EXTRACTION_STATUS_OCR_REQUIRED,
                "branch": "extraction",
                "textAvailable": False,
                "charCount": 0,
                "blockCount": 0,
                "chunkCount": 0,
                "pageCount": 4,
                "warnings": [WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD],
            },
        )

        self.assertEqual(body["status"], EXTRACTION_STATUS_OCR_REQUIRED)
        self.assertEqual(body["pageCount"], 4)
        self.assertEqual(body["warnings"], [WARNING_TEXT_LAYER_COVERAGE_BELOW_THRESHOLD])
        self.assertNotIn("textBucket", body)
        self.assertNotIn("manifestKey", body)
        self.assertNotIn("plainTextKey", body)

    @patch("shared.callback_post.httpx.post")
    def test_post_extraction_callback_sends_signature_header(self, post_mock) -> None:
        captured: dict[str, object] = {}

        def capture_request(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs["headers"]
            content = kwargs["content"]
            captured["body"] = (
                content.decode("utf-8") if isinstance(content, bytes) else content
            )
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
            )

        post_mock.side_effect = capture_request

        with patch.dict(
            "os.environ",
            {
                "EDNODA_CALLBACK_BASE_URL": "https://nick-dev.ednoda.com",
                "SOURCE_DOCUMENT_CALLBACK_SECRET": "test-secret",
            },
            clear=False,
        ):
            post_extraction_callback(
                {
                    "sourceDocumentId": 42,
                    "attemptNumber": 1,
                    "extractionId": 7,
                    "status": EXTRACTION_STATUS_READY,
                    "extractionStrategy": "plain_text",
                    "textBucket": "bucket",
                    "manifestKey": "manifest.json",
                    "plainTextKey": "plain.txt",
                },
            )

        headers = captured["headers"]
        self.assertIn("X-Ednoda-Signature", headers)
        self.assertEqual(headers["User-Agent"], "EdnodaSourceDocumentWorker/1.0")
        self.assertNotIn("test-secret", str(headers))
        self.assertNotIn("test-secret", captured["body"])
        self.assertTrue(
            str(captured["url"]).endswith("/api/source-documents/extraction/callback"),
        )

    @patch("shared.callback_post.try_post_extraction_callback")
    def test_handler_posts_callback_after_txt_extraction(self, callback_mock) -> None:
        text_handler = load_text_extractor_handler_module()

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

        ready_result = {
            "status": EXTRACTION_STATUS_READY,
            "branch": "extraction",
            "textAvailable": True,
            "textBucket": "ednoda-dev-source-document-text",
            "manifestKey": (
                "source-document-text/user/u/document/42/extraction/7/manifest.json"
            ),
            "plainTextKey": (
                "source-document-text/user/u/document/42/extraction/7/plain.txt"
            ),
            "charCount": 120,
            "blockCount": 2,
            "chunkCount": 1,
        }

        with patch.object(
            text_handler,
            "process_text_extraction",
            return_value=ready_result,
        ):
            result = text_handler.handler(event)

        self.assertEqual(result["status"], EXTRACTION_STATUS_READY)
        callback_mock.assert_called_once()
        callback_body = callback_mock.call_args.args[0]
        self.assertEqual(callback_body["status"], EXTRACTION_STATUS_READY)
        self.assertEqual(callback_body["extractionStrategy"], PREVIEW_STRATEGY_PLAIN_TEXT)
        self.assertNotIn("plainText", callback_body)


class NodeCandidatesCallbackPostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = CandidateExtractorEvent(
            environment="dev",
            source_document_id=42,
            owner_user_id="00000000-0000-4000-8000-000000000001",
            original=OriginalFilePointer(
                bucket="ednoda-dev-source-documents",
                key="source-documents/user/u/document/42/original/lesson.txt",
                mime_type="text/plain",
                file_extension=".txt",
                file_size_bytes=32,
            ),
            workflow_execution_arn="arn:aws:states:us-west-2:123:execution:test",
            workflow_execution_row_id=9,
            attempt_number=1,
            original_filename="lesson.txt",
            extraction_id=7,
            plain_text=S3ObjectPointer(
                bucket="ednoda-dev-source-document-text",
                key="source-document-text/user/u/document/42/extraction/7/plain.txt",
            ),
            task_token="task-token-abc",
        )

    def test_resolve_node_candidates_callback_url_from_base(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "EDNODA_CALLBACK_BASE_URL": "https://app.example.com",
                "SOURCE_DOCUMENT_NODE_CANDIDATES_CALLBACK_URL": "",
            },
            clear=False,
        ):
            url = resolve_node_candidates_callback_url()
        self.assertEqual(
            url,
            "https://app.example.com/api/source-documents/node-candidates/callback",
        )

    def test_build_node_candidates_callback_body_includes_version_and_candidates(
        self,
    ) -> None:
        body = build_node_candidates_callback_body(
            self.event,
            {
                "status": "ready",
                "candidates": [
                    {
                        "candidateType": "vocab",
                        "text": "term: definition",
                        "normalizedText": "term definition",
                    },
                ],
                "warnings": ["no_candidates_found"],
            },
        )
        self.assertEqual(
            body["version"],
            "source-document-candidate-extraction-result.v1",
        )
        self.assertEqual(body["sourceDocumentId"], 42)
        self.assertEqual(body["extractionId"], 7)
        self.assertEqual(body["taskToken"], "task-token-abc")
        self.assertEqual(len(body["candidates"]), 1)

    def test_post_node_candidates_callback_sends_hmac_signature(self) -> None:
        body = build_node_candidates_callback_body(
            self.event,
            {"status": "ready", "candidates": [], "warnings": []},
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "SOURCE_DOCUMENT_NODE_CANDIDATES_CALLBACK_URL": (
                        "https://app.example.com/api/source-documents/node-candidates/callback"
                    ),
                    "SOURCE_DOCUMENT_CALLBACK_SECRET": "test-secret",
                },
                clear=False,
            ),
            patch("shared.callback_post.httpx.post") as post_mock,
        ):
            post_mock.return_value = httpx.Response(
                200,
                request=httpx.Request(
                    "POST",
                    "https://app.example.com/api/source-documents/node-candidates/callback",
                ),
            )
            post_node_candidates_callback(body)

        post_mock.assert_called_once()
        call_kwargs = post_mock.call_args.kwargs
        headers = call_kwargs["headers"]
        signature_header = headers.get("X-Ednoda-Signature")
        self.assertIsNotNone(signature_header)
        self.assertTrue(signature_header)


if __name__ == "__main__":
    unittest.main()
