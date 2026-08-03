"""Upload controls and non-executing PDF safety inspection."""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePath
from uuid import uuid4

from fastapi import UploadFile

from chna_extractor.config import Settings
from chna_extractor.errors import InvalidPdfError, UploadTooLargeError

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
_ALLOWED_CONTENT_TYPES = {"application/pdf", "application/octet-stream", ""}


@dataclass(frozen=True, slots=True)
class SavedUpload:
    path: Path
    original_filename: str
    fingerprint: str
    size_bytes: int


def safe_display_filename(filename: str | None) -> str:
    raw = filename or "report.pdf"
    if PurePath(raw).name != raw or "/" in raw or "\\" in raw:
        raise InvalidPdfError("Upload filenames may not contain paths.")
    cleaned = _SAFE_FILENAME.sub("_", raw).strip(" .")[:150]
    if not cleaned.casefold().endswith(".pdf"):
        raise InvalidPdfError("Only .pdf files are accepted.")
    return cleaned or "report.pdf"


def validate_pdf_signature(data: bytes) -> None:
    if len(data) < 8 or not data.startswith(b"%PDF-"):
        raise InvalidPdfError("The file does not begin with a PDF signature.")
    if b"%%EOF" not in data[-4096:]:
        raise InvalidPdfError("The PDF is truncated or missing its end marker.")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def save_upload(upload: UploadFile, settings: Settings) -> SavedUpload:
    filename = safe_display_filename(upload.filename)
    content_type = (upload.content_type or "").split(";", maxsplit=1)[0].strip().casefold()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidPdfError("Only application/pdf uploads are accepted.")

    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise UploadTooLargeError()
        chunks.append(chunk)
    data = b"".join(chunks)
    validate_pdf_signature(data)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    destination = settings.upload_dir.resolve() / f"{uuid4().hex}.pdf"
    if settings.upload_dir.resolve() not in destination.parents:
        raise InvalidPdfError("Invalid upload destination.")
    await asyncio.to_thread(destination.write_bytes, data)
    return SavedUpload(destination, filename, sha256_bytes(data), size)


def validate_local_pdf(path: Path, settings: Settings) -> SavedUpload:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise InvalidPdfError("The path is not a file.")
    size = resolved.stat().st_size
    if size > settings.max_upload_bytes:
        raise UploadTooLargeError()
    data = resolved.read_bytes()
    validate_pdf_signature(data)
    return SavedUpload(resolved, safe_display_filename(resolved.name), sha256_bytes(data), size)
