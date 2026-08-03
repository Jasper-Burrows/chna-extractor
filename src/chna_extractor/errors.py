"""Sanitized application exceptions safe to expose through the API and CLI."""

from __future__ import annotations


class ChnaError(Exception):
    code = "internal_error"
    user_message = "The extraction could not be completed."
    status_code = 500

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.user_message)


class InvalidPdfError(ChnaError):
    code = "invalid_pdf"
    user_message = "The uploaded file is not a valid, supported PDF."
    status_code = 422


class UnsafePdfError(ChnaError):
    code = "unsafe_pdf"
    user_message = "The PDF contains an unsupported active or embedded payload."
    status_code = 422


class UploadTooLargeError(ChnaError):
    code = "upload_too_large"
    user_message = "The PDF exceeds the configured upload limit."
    status_code = 413


class PdfPageLimitError(ChnaError):
    code = "pdf_page_limit"
    user_message = "The PDF exceeds the configured page limit."
    status_code = 422


class EmptyDocumentError(ChnaError):
    code = "empty_document"
    user_message = "No readable text was found in the PDF. Enable OCR for scanned reports."
    status_code = 422


class OcrUnavailableError(ChnaError):
    code = "ocr_unavailable"
    user_message = "OCR was requested but Tesseract is not installed or did not complete."
    status_code = 503


class LiveModeRequiredError(ChnaError):
    code = "openai_key_required"
    user_message = (
        "This PDF requires live extraction. Set CHNA_OPENAI_API_KEY to a newly issued key, "
        "or use the bundled offline demo."
    )
    status_code = 422


class BudgetExceededError(ChnaError):
    code = "budget_exceeded"
    user_message = "The estimated request cost exceeds the configured safety budget."
    status_code = 422


class ExtractionFailedError(ChnaError):
    code = "extraction_failed"
    user_message = "The model did not return a valid extraction after the bounded retry."
    status_code = 502


class JobNotFoundError(ChnaError):
    code = "job_not_found"
    user_message = "No extraction job was found for that identifier."
    status_code = 404


class JobNotReadyError(ChnaError):
    code = "job_not_ready"
    user_message = "The extraction result is not ready yet."
    status_code = 409


class InvalidResultEditError(ChnaError):
    code = "invalid_result_edit"
    user_message = "The review must preserve the extracted record count and server provenance."
    status_code = 422
