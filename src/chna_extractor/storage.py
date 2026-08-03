"""SQLite job, progress, result, checkpoint, and cache persistence."""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite

from chna_extractor.errors import InvalidResultEditError, JobNotFoundError, JobNotReadyError
from chna_extractor.models import (
    EvidenceMethod,
    ExtractionMode,
    ExtractionResult,
    ExtractionWarning,
    FieldEvidence,
    HospitalRecordEdit,
    JobResponse,
    JobStatus,
    ProgressEvent,
    ProgressEvents,
    ResultEditRequest,
    WarningSeverity,
    utc_now,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    extractor_key TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL CHECK(progress BETWEEN 0 AND 100),
    message TEXT NOT NULL,
    error_code TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint, extractor_key);
CREATE TABLE IF NOT EXISTS events (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    progress INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(job_id, sequence)
);
CREATE TABLE IF NOT EXISTS result_cache (
    cache_key TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class StoredJob:
    id: str
    mode: ExtractionMode
    source_filename: str
    stored_path: Path
    fingerprint: str
    extractor_key: str
    status: JobStatus
    progress: int
    message: str
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class JobStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            self.database_path.parent.chmod(0o700)
        async with self._connect() as connection:
            await connection.executescript(_SCHEMA)
            await connection.commit()
        with suppress(OSError):
            os.chmod(self.database_path, 0o600)

    def _connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self.database_path)

    async def create_job(
        self,
        *,
        job_id: str,
        mode: ExtractionMode,
        source_filename: str,
        stored_path: Path,
        fingerprint: str,
        extractor_key: str,
    ) -> JobResponse:
        now = utc_now().isoformat()
        async with self._connect() as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute(
                """INSERT INTO jobs
                (id, mode, source_filename, stored_path, fingerprint, extractor_key, status,
                 progress, message, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    mode.value,
                    source_filename,
                    str(stored_path),
                    fingerprint,
                    extractor_key,
                    JobStatus.QUEUED.value,
                    0,
                    "Queued for extraction",
                    now,
                    now,
                ),
            )
            await connection.execute(
                """INSERT INTO events
                (job_id, sequence, stage, message, progress, created_at)
                VALUES (?, 1, 'queued', 'Queued for extraction', 0, ?)""",
                (job_id, now),
            )
            await connection.commit()
        return await self.get_job(job_id)

    async def get_stored_job(self, job_id: str) -> StoredJob:
        async with self._connect() as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
        if row is None:
            raise JobNotFoundError()
        return _row_to_stored(row)

    async def get_job(self, job_id: str) -> JobResponse:
        return _to_response(await self.get_stored_job(job_id))

    async def add_event(
        self, job_id: str, *, stage: str, message: str, progress: int
    ) -> ProgressEvent:
        now = utc_now().isoformat()
        async with self._connect() as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            cursor = await connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE job_id = ?", (job_id,)
            )
            sequence_row = await cursor.fetchone()
            sequence = int(sequence_row[0]) if sequence_row else 1
            await connection.execute(
                """INSERT INTO events
                (job_id, sequence, stage, message, progress, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (job_id, sequence, stage, message, progress, now),
            )
            await connection.execute(
                """UPDATE jobs SET progress = ?, message = ?, updated_at = ? WHERE id = ?""",
                (progress, message, now, job_id),
            )
            await connection.commit()
        return ProgressEvent(
            sequence=sequence,
            stage=stage,
            message=message,
            progress=progress,
            created_at=datetime.fromisoformat(now),
        )

    async def mark_running(self, job_id: str) -> None:
        await self._set_status(job_id, JobStatus.RUNNING)

    async def complete(self, job_id: str, result: ExtractionResult) -> None:
        now = utc_now().isoformat()
        payload = result.model_dump_json()
        async with self._connect() as connection:
            await connection.execute(
                """UPDATE jobs SET status = ?, progress = 100, message = ?, result_json = ?,
                error_code = NULL, updated_at = ? WHERE id = ?""",
                (JobStatus.SUCCEEDED.value, "Extraction complete", payload, now, job_id),
            )
            await connection.commit()
        await self.add_event(job_id, stage="complete", message="Extraction complete", progress=100)

    async def fail(self, job_id: str, *, code: str, message: str) -> None:
        now = utc_now().isoformat()
        async with self._connect() as connection:
            await connection.execute(
                """UPDATE jobs SET status = ?, message = ?, error_code = ?, updated_at = ?
                WHERE id = ?""",
                (JobStatus.FAILED.value, message, code, now, job_id),
            )
            await connection.commit()
        job = await self.get_stored_job(job_id)
        await self.add_event(job_id, stage="failed", message=message, progress=job.progress)

    async def get_events(self, job_id: str) -> ProgressEvents:
        await self.get_stored_job(job_id)
        async with self._connect() as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT * FROM events WHERE job_id = ? ORDER BY sequence", (job_id,)
            )
            rows = await cursor.fetchall()
        return ProgressEvents(
            items=[
                ProgressEvent(
                    sequence=row["sequence"],
                    stage=row["stage"],
                    message=row["message"],
                    progress=row["progress"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]
        )

    async def get_result(self, job_id: str) -> ExtractionResult:
        async with self._connect() as connection:
            cursor = await connection.execute(
                "SELECT status, result_json FROM jobs WHERE id = ?", (job_id,)
            )
            row = await cursor.fetchone()
        if row is None:
            raise JobNotFoundError()
        if row[0] != JobStatus.SUCCEEDED.value or row[1] is None:
            raise JobNotReadyError()
        return ExtractionResult.model_validate_json(row[1])

    async def update_result(self, job_id: str, edit: ResultEditRequest) -> ExtractionResult:
        current = await self.get_result(job_id)
        if len(edit.records) != len(current.records):
            raise InvalidResultEditError()
        updated = current.model_copy(deep=True)
        changed_fields: list[str] = []
        editable_fields = tuple(HospitalRecordEdit.model_fields)
        for record_index, (record, requested) in enumerate(
            zip(updated.records, edit.records, strict=True)
        ):
            for field in editable_fields:
                value = getattr(requested, field)
                if getattr(record, field) == value:
                    continue
                setattr(record, field, value)
                record.evidence[field] = [
                    FieldEvidence(
                        page=None,
                        excerpt="Value replaced during human review; verify it independently.",
                        confidence=0.0,
                        method=EvidenceMethod.USER_EDIT,
                    )
                ]
                record.warnings = [
                    warning
                    for warning in record.warnings
                    if not (warning.code == "user_edited_field" and warning.field == field)
                ]
                record.warnings.append(
                    ExtractionWarning(
                        code="user_edited_field",
                        message="Human review replaced this field; original evidence is stale.",
                        severity=WarningSeverity.INFO,
                        field=field,
                    )
                )
                changed_fields.append(f"{record_index}:{field}")
        if not changed_fields:
            return current
        if not any(warning.code == "user_review_applied" for warning in updated.warnings):
            updated.warnings.append(
                ExtractionWarning(
                    code="user_review_applied",
                    message="One or more values were replaced during human review.",
                    severity=WarningSeverity.INFO,
                )
            )
        async with self._connect() as connection:
            await connection.execute(
                "UPDATE jobs SET result_json = ?, updated_at = ? WHERE id = ?",
                (updated.model_dump_json(), utc_now().isoformat(), job_id),
            )
            await connection.commit()
        await self.add_event(job_id, stage="edited", message="Result updated by user", progress=100)
        return updated

    async def get_cached(self, cache_key: str) -> ExtractionResult | None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                "SELECT result_json FROM result_cache WHERE cache_key = ?", (cache_key,)
            )
            row = await cursor.fetchone()
        return ExtractionResult.model_validate_json(row[0]) if row else None

    async def put_cached(self, cache_key: str, result: ExtractionResult) -> None:
        async with self._connect() as connection:
            await connection.execute(
                """INSERT INTO result_cache(cache_key, result_json, created_at) VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET result_json = excluded.result_json,
                created_at = excluded.created_at""",
                (cache_key, result.model_dump_json(), utc_now().isoformat()),
            )
            await connection.commit()

    async def pending_jobs(self) -> list[StoredJob]:
        async with self._connect() as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT * FROM jobs WHERE status IN (?, ?) ORDER BY created_at",
                (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            )
            rows = await cursor.fetchall()
        return [_row_to_stored(row) for row in rows]

    async def is_ready(self) -> bool:
        try:
            async with self._connect() as connection:
                cursor = await connection.execute("SELECT 1")
                return (await cursor.fetchone()) is not None
        except aiosqlite.Error:
            return False

    async def _set_status(self, job_id: str, status: JobStatus) -> None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, utc_now().isoformat(), job_id),
            )
            await connection.commit()
        if cursor.rowcount == 0:
            raise JobNotFoundError()


def _row_to_stored(row: aiosqlite.Row) -> StoredJob:
    return StoredJob(
        id=row["id"],
        mode=ExtractionMode(row["mode"]),
        source_filename=row["source_filename"],
        stored_path=Path(row["stored_path"]),
        fingerprint=row["fingerprint"],
        extractor_key=row["extractor_key"],
        status=JobStatus(row["status"]),
        progress=row["progress"],
        message=row["message"],
        error_code=row["error_code"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _to_response(job: StoredJob) -> JobResponse:
    base = f"/api/v1/extractions/{job.id}"
    return JobResponse(
        id=job.id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        mode=job.mode,
        source_filename=job.source_filename,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error_code=job.error_code,
        links={
            "self": base,
            "events": f"{base}/events",
            "result": f"{base}/result",
            "export": f"{base}/export",
        },
    )
