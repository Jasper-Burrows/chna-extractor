from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from chna_extractor.config import Settings
from chna_extractor.errors import (
    EmptyDocumentError,
    InvalidPdfError,
    OcrUnavailableError,
    PdfPageLimitError,
    UnsafePdfError,
    UploadTooLargeError,
)
from chna_extractor.pdf import _reject_active_content, _run_tesseract, inspect_and_extract
from chna_extractor.security import (
    safe_display_filename,
    save_upload,
    sha256_bytes,
    validate_local_pdf,
    validate_pdf_signature,
)


def test_filename_and_signature_validation() -> None:
    assert safe_display_filename("my report.pdf") == "my report.pdf"
    with pytest.raises(InvalidPdfError):
        safe_display_filename("../secret.pdf")
    with pytest.raises(InvalidPdfError):
        safe_display_filename("report.txt")
    with pytest.raises(InvalidPdfError):
        validate_pdf_signature(b"not-a-pdf")
    with pytest.raises(InvalidPdfError):
        validate_pdf_signature(b"%PDF-1.4\ntruncated")


def test_local_pdf_and_text_extraction(make_pdf, settings: Settings) -> None:
    path = make_pdf(text="Community health assessment evidence " * 10)
    saved = validate_local_pdf(path, settings)
    assert saved.path == path.resolve()
    assert saved.fingerprint == sha256_bytes(path.read_bytes())
    content = inspect_and_extract(path, settings)
    assert content.page_count == 1
    assert "Community health" in content.prompt_text
    assert not content.used_ocr


def test_pdf_page_limit_and_empty_document(make_pdf, settings: Settings) -> None:
    with pytest.raises(PdfPageLimitError):
        inspect_and_extract(make_pdf(pages=2), settings.model_copy(update={"max_pdf_pages": 1}))
    with pytest.raises(EmptyDocumentError):
        inspect_and_extract(make_pdf(text=""), settings)


def test_ocr_unavailable_is_explicit(make_pdf, settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr("chna_extractor.pdf.shutil.which", lambda _: None)
    with pytest.raises(OcrUnavailableError):
        inspect_and_extract(make_pdf(text=""), settings.model_copy(update={"enable_ocr": True}))


def test_ocr_success_contract(make_pdf, settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr("chna_extractor.pdf.shutil.which", lambda _: "/usr/bin/tesseract")
    monkeypatch.setattr(
        "chna_extractor.pdf._run_tesseract",
        lambda *_args: "Synthetic OCR evidence " * 20,
    )
    content = inspect_and_extract(
        make_pdf(text=""), settings.model_copy(update={"enable_ocr": True})
    )
    assert content.used_ocr
    assert content.pages[0].method.value == "ocr"
    assert "Synthetic OCR evidence" in content.pages[0].text


def test_ocr_subprocess_timeout_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("tesseract", timeout=1)

    monkeypatch.setattr("subprocess.run", timeout)
    with pytest.raises(OcrUnavailableError):
        _run_tesseract(tmp_path / "page.png", 1, "/usr/bin/tesseract")


def test_malformed_and_active_pdf_rejected(tmp_path: Path, settings: Settings) -> None:
    malformed = tmp_path / "bad.pdf"
    malformed.write_bytes(b"%PDF-1.4\ngarbage\n%%EOF\n")
    with pytest.raises(InvalidPdfError):
        inspect_and_extract(malformed, settings)

    class ActiveDocument:
        @staticmethod
        def xref_length() -> int:
            return 2

        @staticmethod
        def xref_object(_xref: int, compressed: bool = True) -> str:
            assert compressed
            return "<< /JavaScript 2 0 R >>"

    with pytest.raises(UnsafePdfError):
        _reject_active_content(ActiveDocument())  # type: ignore[arg-type]

    class OversizedObjectTable:
        @staticmethod
        def xref_length() -> int:
            return 25_001

    with pytest.raises(UnsafePdfError, match="object table"):
        _reject_active_content(OversizedObjectTable())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_upload_enforces_content_type_size_and_generated_path(
    make_pdf, settings: Settings
) -> None:
    data = make_pdf().read_bytes()
    upload = UploadFile(
        file=BytesIO(data),
        filename="safe.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    saved = await save_upload(upload, settings)
    assert saved.path.parent == settings.upload_dir.resolve()
    assert saved.path.name != "safe.pdf"

    wrong_type = UploadFile(
        file=BytesIO(data),
        filename="safe.pdf",
        headers=Headers({"content-type": "text/plain"}),
    )
    with pytest.raises(InvalidPdfError):
        await save_upload(wrong_type, settings)

    tiny = settings.model_copy(update={"max_upload_mb": 1})
    huge_data = b"%PDF-1.4\n" + b"x" * (1024 * 1024) + b"\n%%EOF\n"
    huge = UploadFile(
        file=BytesIO(huge_data),
        filename="large.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(UploadTooLargeError):
        await save_upload(huge, tiny)
