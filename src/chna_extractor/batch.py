"""Concurrent batch execution with an atomic, resumable checkpoint file."""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from chna_extractor.costs import estimate_cost
from chna_extractor.errors import BudgetExceededError
from chna_extractor.exporters import export_json, export_legacy_csv
from chna_extractor.models import ExtractionMode
from chna_extractor.pdf import extract_pdf
from chna_extractor.security import SavedUpload, validate_local_pdf
from chna_extractor.service import ExtractionService


class BatchCheckpoint(BaseModel):
    version: int = 2
    completed: dict[str, str] = Field(default_factory=dict)
    failed: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> BatchCheckpoint:
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


@dataclass(slots=True)
class _BatchItem:
    path: Path
    destination: Path
    work_key: str


@dataclass(slots=True)
class _BatchGroup:
    upload: SavedUpload
    items: list[_BatchItem]


async def run_batch(
    *,
    files: list[Path],
    output_dir: Path,
    checkpoint_path: Path,
    mode: ExtractionMode,
    output_format: str,
    service: ExtractionService,
    source_root: Path | None = None,
) -> BatchCheckpoint:
    checkpoint = BatchCheckpoint.load(checkpoint_path)
    await asyncio.to_thread(output_dir.mkdir, parents=True, exist_ok=True)
    checkpoint_lock = asyncio.Lock()
    suffix = ".json" if output_format == "json" else ".csv"
    root = _source_root(files, source_root)
    groups: dict[str, _BatchGroup] = {}

    # Validation is isolated per path so one malformed file cannot cancel the batch.
    for path in files:
        failure_key = _path_failure_key(path, root)
        try:
            upload = validate_local_pdf(path, service.settings)
            destination = _destination_for(path, root, output_dir, suffix)
            work_key = _work_key(upload.fingerprint, destination.relative_to(output_dir))
            checkpoint.failed.pop(failure_key, None)
            group = groups.setdefault(upload.fingerprint, _BatchGroup(upload=upload, items=[]))
            group.items.append(_BatchItem(path=path, destination=destination, work_key=work_key))
        except Exception as exc:
            checkpoint.failed[failure_key] = type(exc).__name__
    checkpoint.save(checkpoint_path)

    pending: list[_BatchGroup] = []
    batch_worst_case_cost = 0.0
    for group in groups.values():
        unfinished = [
            item
            for item in group.items
            if item.work_key not in checkpoint.completed or not item.destination.exists()
        ]
        if not unfinished:
            continue
        group.items = unfinished
        try:
            resolved_mode = service.resolve_mode(group.upload.path, mode)
            if resolved_mode is ExtractionMode.LIVE:
                content = await extract_pdf(group.upload.path, service.settings)
                batch_worst_case_cost += estimate_cost(
                    content, service.settings
                ).worst_case_cost_usd
            pending.append(group)
        except Exception as exc:
            for item in group.items:
                checkpoint.failed[item.work_key] = type(exc).__name__
    checkpoint.save(checkpoint_path)
    if batch_worst_case_cost > service.settings.total_budget_usd:
        raise BudgetExceededError()

    async def process(group: _BatchGroup) -> None:
        try:
            job = await service.submit(group.upload, mode)
            result = await service.wait(job.id)
            payload = export_json(result) if output_format == "json" else export_legacy_csv(result)
            for item in group.items:
                await asyncio.to_thread(_write_atomic, item.destination, payload)
            async with checkpoint_lock:
                for item in group.items:
                    checkpoint.completed[item.work_key] = item.destination.relative_to(
                        output_dir
                    ).as_posix()
                    checkpoint.failed.pop(item.work_key, None)
                checkpoint.save(checkpoint_path)
        except Exception as exc:
            async with checkpoint_lock:
                for item in group.items:
                    checkpoint.failed[item.work_key] = type(exc).__name__
                checkpoint.save(checkpoint_path)

    await asyncio.gather(*(process(group) for group in pending))
    return checkpoint


def _source_root(files: list[Path], configured: Path | None) -> Path:
    if configured is not None:
        return configured.resolve()
    parents = [str(path.resolve().parent) for path in files]
    return Path(os.path.commonpath(parents)).resolve() if parents else Path.cwd().resolve()


def _destination_for(path: Path, root: Path, output_dir: Path, suffix: str) -> Path:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        path_hash = hashlib.sha256(str(resolved).encode()).hexdigest()[:10]
        relative = Path(f"{resolved.stem}-{path_hash}{resolved.suffix}")
    destination = output_dir / relative.with_suffix(suffix)
    if output_dir.resolve() not in destination.resolve().parents:
        raise ValueError("batch output escaped the configured output directory")
    return destination


def _work_key(fingerprint: str, relative_destination: Path) -> str:
    value = f"{fingerprint}:{relative_destination.as_posix()}"
    return hashlib.sha256(value.encode()).hexdigest()


def _path_failure_key(path: Path, root: Path) -> str:
    try:
        identity = path.resolve().relative_to(root).as_posix()
    except ValueError:
        identity = str(path.resolve())
    return "path-" + hashlib.sha256(identity.encode()).hexdigest()


def _write_atomic(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)
