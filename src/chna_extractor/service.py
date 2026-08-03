"""Application service coordinating validation, jobs, extraction, enrichment, and caching."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from chna_extractor.config import Settings
from chna_extractor.costs import merge_usage
from chna_extractor.enrichment import (
    GoogleMapsEnricher,
    NoopEnricher,
    OpenAIWebSearchEnricher,
    RecordEnricher,
)
from chna_extractor.errors import (
    ChnaError,
    ExtractionFailedError,
    LiveModeRequiredError,
)
from chna_extractor.extractors import DemoExtractor, OpenAIExtractor, is_demo_fixture
from chna_extractor.logging import get_logger
from chna_extractor.models import (
    ExtractionMode,
    ExtractionResult,
    ExtractionWarning,
    HospitalRecord,
    JobResponse,
    JobStatus,
    UsageSummary,
    WarningSeverity,
    utc_now,
)
from chna_extractor.pdf import extract_pdf
from chna_extractor.security import SavedUpload, sha256_bytes
from chna_extractor.storage import JobStore, StoredJob


class ExtractionService:
    def __init__(self, settings: Settings, store: JobStore) -> None:
        self.settings = settings
        self.store = store
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)
        self._tasks: set[asyncio.Task[None]] = set()
        self.log = get_logger()

    async def submit(self, upload: SavedUpload, requested_mode: ExtractionMode) -> JobResponse:
        try:
            mode = self.resolve_mode(upload.path, requested_mode)
            pipeline_fingerprint = _pipeline_fingerprint(self.settings, mode)
            extractor_key = (
                f"offline:v2:{pipeline_fingerprint}"
                if mode is ExtractionMode.OFFLINE
                else f"openai:{self.settings.openai_model}:schema-v2:{pipeline_fingerprint}"
            )
            job_id = uuid4().hex
            job = await self.store.create_job(
                job_id=job_id,
                mode=mode,
                source_filename=upload.original_filename,
                stored_path=upload.path,
                fingerprint=upload.fingerprint,
                extractor_key=extractor_key,
            )
            cache_key = _cache_key(upload.fingerprint, extractor_key)
            cached = await self.store.get_cached(cache_key)
            if cached is not None:
                cache_warning = ExtractionWarning(
                    code="cache_hit",
                    message=(
                        "Reused a validated result for the identical PDF and "
                        "extraction configuration."
                    ),
                    severity=WarningSeverity.INFO,
                )
                reused = cached.model_copy(
                    update={
                        "job_id": job_id,
                        "source_file": upload.original_filename,
                        "completed_at": utc_now(),
                        "warnings": [*cached.warnings, cache_warning],
                    },
                    deep=True,
                )
                await self.store.complete(job_id, reused)
                await self._delete_private_upload(upload.path)
                return await self.store.get_job(job_id)
        except Exception:
            # A rejected preflight must not orphan an API upload. The containment check protects CLI
            # source files and the packaged fixture from deletion.
            await self._delete_private_upload(upload.path)
            raise

        self._schedule(self._run(job_id, cache_key))
        return job

    async def submit_demo(self) -> JobResponse:
        path = self.settings.fixture_path
        data = path.read_bytes()
        return await self.submit(
            SavedUpload(
                path=path,
                original_filename=path.name,
                fingerprint=sha256_bytes(data),
                size_bytes=len(data),
            ),
            ExtractionMode.OFFLINE,
        )

    async def resume_pending(self) -> None:
        for job in await self.store.pending_jobs():
            if not job.stored_path.exists():
                await self.store.fail(
                    job.id,
                    code="source_missing",
                    message="The private source PDF is no longer available; submit it again.",
                )
                continue
            self._schedule(self._run(job.id, _cache_key(job.fingerprint, job.extractor_key)))

    async def wait(self, job_id: str) -> ExtractionResult:
        while True:
            job = await self.store.get_job(job_id)
            if job.status is JobStatus.SUCCEEDED:
                return await self.store.get_result(job_id)
            if job.status is JobStatus.FAILED:
                raise ExtractionFailedError(job.message)
            await asyncio.sleep(0.025)

    def resolve_mode(self, path: Path, requested: ExtractionMode) -> ExtractionMode:
        demo = is_demo_fixture(path, self.settings)
        if requested is ExtractionMode.OFFLINE:
            if not demo:
                raise LiveModeRequiredError()
            return ExtractionMode.OFFLINE
        if requested is ExtractionMode.LIVE:
            if not self.settings.live_available:
                raise LiveModeRequiredError()
            return ExtractionMode.LIVE
        if demo:
            return ExtractionMode.OFFLINE
        if self.settings.live_available:
            return ExtractionMode.LIVE
        raise LiveModeRequiredError()

    # Kept as a small compatibility boundary for callers from the pre-1.0 implementation.
    def _resolve_mode(self, path: Path, requested: ExtractionMode) -> ExtractionMode:
        return self.resolve_mode(path, requested)

    def _schedule(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task: asyncio.Task[None] = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, job_id: str, cache_key: str) -> None:
        job: StoredJob | None = None
        try:
            job = await self.store.get_stored_job(job_id)
            async with self._semaphore:
                await self.store.mark_running(job_id)
                await self.store.add_event(
                    job_id, stage="validation", message="Inspecting PDF safely", progress=10
                )
                content = await extract_pdf(job.stored_path, self.settings)
                await self.store.add_event(
                    job_id,
                    stage="text",
                    message=f"Extracted text from {content.page_count} page(s)",
                    progress=35,
                )
                extractor = (
                    DemoExtractor()
                    if job.mode is ExtractionMode.OFFLINE
                    else OpenAIExtractor(self.settings)
                )
                await self.store.add_event(
                    job_id,
                    stage="extraction",
                    message=(
                        "Running deterministic demo extraction"
                        if job.mode is ExtractionMode.OFFLINE
                        else "Requesting schema-constrained live extraction"
                    ),
                    progress=55,
                )
                records, usage, warnings = await extractor.extract(content, job.source_filename)
                await self.store.add_event(
                    job_id,
                    stage="validation",
                    message="Validating evidence and fields",
                    progress=80,
                )
                records, enrichment_usage, enrichment_warnings = await self._enrich(records, usage)
                result = ExtractionResult(
                    job_id=job_id,
                    source_file=job.source_filename,
                    records=records,
                    usage=merge_usage(usage, enrichment_usage),
                    warnings=[*warnings, *enrichment_warnings],
                )
                await self.store.put_cached(cache_key, result)
                await self.store.complete(job_id, result)
        except ChnaError as exc:
            await self.store.fail(job_id, code=exc.code, message=exc.user_message)
        except Exception as exc:  # defensive boundary; details stay only in structured local logs
            self.log.error("job_failed", job_id=job_id, exception_type=type(exc).__name__)
            await self.store.fail(
                job_id,
                code="internal_error",
                message=(
                    "The extraction could not be completed. Review server logs using the job ID."
                ),
            )
        finally:
            if job is not None:
                await self._delete_private_upload(job.stored_path)

    async def _enrich(
        self, records: list[HospitalRecord], current_usage: UsageSummary
    ) -> tuple[list[HospitalRecord], UsageSummary | None, list[ExtractionWarning]]:
        enricher: RecordEnricher
        if self.settings.enable_google_maps and self.settings.google_maps_api_key:
            enricher = GoogleMapsEnricher(self.settings)
        else:
            enricher = NoopEnricher()
        enriched: list[HospitalRecord] = []
        warnings: list[ExtractionWarning] = []
        for record in records:
            try:
                enriched.append(await enricher.enrich(record))
            except (httpx.HTTPError, ValueError):
                enriched.append(record)
                warnings.append(
                    ExtractionWarning(
                        code="enrichment_failed",
                        message=(
                            "Optional address enrichment failed; extracted fields were preserved."
                        ),
                    )
                )
        web_usage: UsageSummary | None = None
        if self.settings.enable_web_search and self.settings.live_available:
            web_enricher = OpenAIWebSearchEnricher(self.settings)
            enriched, web_usage, web_warnings = await web_enricher.enrich(enriched, current_usage)
            warnings.extend(web_warnings)
        return enriched, web_usage, warnings

    async def _delete_private_upload(self, path: Path) -> None:
        if self.settings.retain_uploaded_files or path == self.settings.fixture_path:
            return
        try:
            await asyncio.to_thread(_delete_contained_file, path, self.settings.upload_dir)
        except OSError:
            self.log.warning("upload_cleanup_failed")


def _cache_key(fingerprint: str, extractor_key: str) -> str:
    return hashlib.sha256(f"{fingerprint}:{extractor_key}".encode()).hexdigest()


def _pipeline_fingerprint(settings: Settings, mode: ExtractionMode) -> str:
    """Hash every policy input that can change a stored post-enrichment result."""
    policy = {
        "version": "pipeline-v2",
        "mode": mode.value,
        "model": settings.openai_model if mode is ExtractionMode.LIVE else "offline-v1",
        "max_pdf_pages": settings.max_pdf_pages,
        "ocr": {
            "enabled": settings.enable_ocr,
            "timeout_seconds": settings.ocr_timeout_seconds,
        },
        "google_maps_active": bool(
            settings.enable_google_maps and settings.google_maps_api_key is not None
        ),
        "web_search_active": bool(settings.enable_web_search and settings.live_available),
        "web_search": {
            "reserve_usd": settings.web_search_reserve_usd,
            "max_records": settings.web_search_max_records,
            "max_tool_calls": settings.web_search_max_tool_calls,
        },
        "pricing": {
            "input": settings.input_cost_per_million,
            "cached_input": settings.cached_input_cost_per_million,
            "output": settings.output_cost_per_million,
            "total_budget": settings.total_budget_usd,
        },
    }
    serialized = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _delete_contained_file(path: Path, root: Path) -> None:
    upload_root = root.resolve()
    resolved = path.resolve()
    if upload_root in resolved.parents and resolved.is_file():
        resolved.unlink()
