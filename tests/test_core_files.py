"""Tests for core/files_api.py — FileRef.as_document_block()."""

from core.files_api import FileRef, _guess_media_type
from pathlib import Path


class TestFileRef:
    def test_as_document_block_default(self):
        ref = FileRef(id="file-123", filename="report.pdf")
        block = ref.as_document_block()
        assert block["type"] == "document"
        assert block["source"]["type"] == "file"
        assert block["source"]["file_id"] == "file-123"
        assert block["title"] == "report.pdf"
        assert block["citations"]["enabled"] is True

    def test_as_document_block_custom_title(self):
        ref = FileRef(id="file-456", filename="raw.pdf")
        block = ref.as_document_block(title="ISO 27001 Checklist")
        assert block["title"] == "ISO 27001 Checklist"

    def test_as_document_block_citations_disabled(self):
        ref = FileRef(id="file-789", filename="doc.pdf")
        block = ref.as_document_block(citations=False)
        assert "citations" not in block

    def test_fileref_defaults(self):
        ref = FileRef(id="f1", filename="test.txt")
        assert ref.bytes == 0
        assert ref.created_at == 0
        assert ref.media_type == ""
        assert ref.purpose == "document"

    def test_fileref_file_id_in_source(self):
        ref = FileRef(id="file-abc", filename="x.pdf")
        block = ref.as_document_block()
        assert block["source"]["file_id"] == "file-abc"


class TestGuessMediaType:
    def test_pdf_extension(self):
        assert _guess_media_type(Path("doc.pdf")) == "application/pdf"

    def test_txt_extension(self):
        assert _guess_media_type(Path("notes.txt")) == "text/plain"

    def test_md_extension(self):
        assert _guess_media_type(Path("README.md")) == "text/markdown"

    def test_csv_extension(self):
        assert _guess_media_type(Path("data.csv")) == "text/csv"

    def test_png_extension(self):
        assert _guess_media_type(Path("image.png")) == "image/png"

    def test_docx_extension(self):
        result = _guess_media_type(Path("report.docx"))
        assert "wordprocessingml" in result

    def test_unknown_extension_returns_octet_stream(self):
        assert _guess_media_type(Path("file.xyz")) == "application/octet-stream"
