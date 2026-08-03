"""Bounded PDF inspection, text extraction, and optional OCR fallback."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz

from chna_extractor.config import Settings
from chna_extractor.errors import (
    EmptyDocumentError,
    InvalidPdfError,
    OcrUnavailableError,
    PdfPageLimitError,
    UnsafePdfError,
)
from chna_extractor.models import EvidenceMethod

_ACTIVE_PDF_MARKERS = ("/JavaScript", "/JS", "/Launch", "/EmbeddedFile", "/RichMedia")


@dataclass(frozen=True, slots=True)
class PageText:
    page: int
    text: str
    method: EvidenceMethod


@dataclass(frozen=True, slots=True)
class PdfContent:
    pages: tuple[PageText, ...]
    page_count: int
    character_count: int
    used_ocr: bool

    @property
    def prompt_text(self) -> str:
        return "\n\n".join(f"--- PAGE {item.page} ---\n{item.text}" for item in self.pages)


def inspect_and_extract(path: Path, settings: Settings) -> PdfContent:
    """Read text without following links, opening attachments, or executing actions."""
    try:
        document = fitz.open(path)
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise InvalidPdfError() from exc

    try:
        if document.needs_pass:
            raise InvalidPdfError("Password-protected PDFs are not supported.")
        if document.page_count == 0:
            raise InvalidPdfError("The PDF has no pages.")
        if document.page_count > settings.max_pdf_pages:
            raise PdfPageLimitError()
        _reject_active_content(document)
        pages = tuple(
            PageText(
                page=index + 1,
                text=" ".join(document.load_page(index).get_text("text").split()),
                method=EvidenceMethod.DOCUMENT_TEXT,
            )
            for index in range(document.page_count)
        )
    except (InvalidPdfError, PdfPageLimitError, UnsafePdfError):
        raise
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise InvalidPdfError() from exc
    finally:
        document.close()

    character_count = sum(len(page.text) for page in pages)
    if character_count >= 120:
        return PdfContent(pages, len(pages), character_count, False)
    if not settings.enable_ocr:
        raise EmptyDocumentError()
    return _extract_with_ocr(path, settings, pages)


async def extract_pdf(path: Path, settings: Settings) -> PdfContent:
    return await asyncio.to_thread(inspect_and_extract, path, settings)


def _reject_active_content(document: fitz.Document) -> None:
    # MuPDF never executes these actions here; rejecting them further narrows the accepted input.
    try:
        xref_length = document.xref_length()
        if xref_length > 25_000:
            raise UnsafePdfError("The PDF object table exceeds the safety limit.")
        for xref in range(1, xref_length):
            raw = document.xref_object(xref, compressed=True)
            if any(marker in raw for marker in _ACTIVE_PDF_MARKERS):
                raise UnsafePdfError()
    except UnsafePdfError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise InvalidPdfError("The PDF object table could not be inspected.") from exc


def _extract_with_ocr(
    path: Path, settings: Settings, original_pages: tuple[PageText, ...]
) -> PdfContent:
    tesseract_path = shutil.which("tesseract")
    if tesseract_path is None:
        raise OcrUnavailableError()

    ocr_pages: list[PageText] = []
    document = fitz.open(path)
    try:
        with tempfile.TemporaryDirectory(prefix="chna-ocr-") as temporary_directory:
            temp = Path(temporary_directory)
            for index, original in enumerate(original_pages):
                if len(original.text) >= 80:
                    ocr_pages.append(original)
                    continue
                image_path = temp / f"page-{index + 1}.png"
                pixmap = document.load_page(index).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pixmap.save(image_path)
                ocr_text = _run_tesseract(image_path, settings.ocr_timeout_seconds, tesseract_path)
                ocr_pages.append(
                    PageText(
                        page=index + 1,
                        text=" ".join(ocr_text.split()),
                        method=EvidenceMethod.OCR,
                    )
                )
    finally:
        document.close()

    character_count = sum(len(page.text) for page in ocr_pages)
    if character_count < 120:
        raise EmptyDocumentError()
    return PdfContent(tuple(ocr_pages), len(ocr_pages), character_count, True)


def _run_tesseract(image_path: Path, timeout_seconds: int, executable: str) -> str:
    import subprocess

    try:
        completed = subprocess.run(  # noqa: S603
            [executable, str(image_path), "stdout", "--dpi", "200"],
            capture_output=True,
            check=True,
            timeout=timeout_seconds,
            text=True,
            shell=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise OcrUnavailableError() from exc
    return completed.stdout
