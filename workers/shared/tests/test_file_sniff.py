"""Unit tests for shared file sniffing."""

from __future__ import annotations

import sys
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from shared.file_sniff import validate_source_document_file_content  # noqa: E402


def build_min_docx_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>',
        )
    return buffer.getvalue()


class FileSniffTests(unittest.TestCase):
    def test_rejects_pdf_content_with_csv_extension(self) -> None:
        result = validate_source_document_file_content(
            b"%PDF-1.4 fake",
            file_extension=".csv",
            mime_type="text/csv",
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.error_code, "signature_mismatch")

    def test_accepts_valid_docx_zip(self) -> None:
        result = validate_source_document_file_content(
            build_min_docx_bytes(),
            file_extension=".docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(result.valid)

    def test_accepts_valid_csv(self) -> None:
        result = validate_source_document_file_content(
            b"word,meaning\nhabitat,home\n",
            file_extension=".csv",
            mime_type="text/csv",
        )
        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()
