"""Command-line interface sharing the same validation and job path as the web API."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Annotated, Any

import typer

from chna_extractor.batch import run_batch
from chna_extractor.config import Settings, get_settings
from chna_extractor.costs import estimate_cost
from chna_extractor.errors import ChnaError
from chna_extractor.exporters import export_json, export_legacy_csv
from chna_extractor.models import ExtractionMode
from chna_extractor.pdf import extract_pdf
from chna_extractor.security import validate_local_pdf
from chna_extractor.service import ExtractionService
from chna_extractor.storage import JobStore

app = typer.Typer(
    name="chna",
    help="Extract evidence-backed hospital data from CHNA PDFs.",
    no_args_is_help=True,
)


def _settings_with_concurrency(concurrency: int | None = None) -> Settings:
    settings = get_settings()
    if concurrency is not None:
        return settings.model_copy(update={"max_concurrent_jobs": concurrency})
    return settings


async def _service(settings: Settings) -> ExtractionService:
    store = JobStore(settings.database_path)
    await store.initialize()
    service = ExtractionService(settings, store)
    await service.resume_pending()
    return service


@app.command()
def extract(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    format: Annotated[str, typer.Option("--format", case_sensitive=False)] = "json",
    mode: Annotated[ExtractionMode, typer.Option("--mode")] = ExtractionMode.AUTO,
) -> None:
    """Extract one PDF. Arbitrary reports require a newly issued OpenAI key."""
    if format not in {"json", "csv"}:
        raise typer.BadParameter("format must be json or csv")

    async def run() -> bytes:
        settings = _settings_with_concurrency()
        upload = validate_local_pdf(pdf, settings)
        service = await _service(settings)
        job = await service.submit(upload, mode)
        result = await service.wait(job.id)
        return export_json(result) if format == "json" else export_legacy_csv(result)

    _run_and_write(run(), output)


@app.command()
def batch(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False, readable=True)],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")] = Path("chna-output"),
    format: Annotated[str, typer.Option("--format", case_sensitive=False)] = "json",
    mode: Annotated[ExtractionMode, typer.Option("--mode")] = ExtractionMode.AUTO,
    concurrency: Annotated[int, typer.Option(min=1, max=8)] = 2,
    recursive: Annotated[bool, typer.Option("--recursive/--no-recursive")] = False,
    checkpoint: Annotated[Path | None, typer.Option("--checkpoint")] = None,
) -> None:
    """Process a directory concurrently, resuming from an atomic checkpoint."""
    if format not in {"json", "csv"}:
        raise typer.BadParameter("format must be json or csv")
    files = sorted(directory.rglob("*.pdf") if recursive else directory.glob("*.pdf"))
    if not files:
        typer.echo("No PDF files found.")
        raise typer.Exit(code=1)

    async def run() -> None:
        settings = _settings_with_concurrency(concurrency)
        service = await _service(settings)
        state = await run_batch(
            files=files,
            output_dir=output_dir,
            checkpoint_path=checkpoint or output_dir / ".chna-checkpoint.json",
            mode=mode,
            output_format=format,
            service=service,
            source_root=directory,
        )
        typer.echo(f"Completed: {len(state.completed)}; failed: {len(state.failed)}")
        if state.failed:
            raise typer.Exit(code=1)

    _run(run())


@app.command()
def estimate(
    pdf: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Inspect a PDF locally and show conservative token/cost assumptions."""

    async def run() -> None:
        settings = _settings_with_concurrency()
        upload = validate_local_pdf(pdf, settings)
        content = await extract_pdf(upload.path, settings)
        typer.echo(estimate_cost(content, settings).model_dump_json(indent=2))

    _run(run())


@app.command()
def demo(
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Run the real job/export path with the bundled, deterministic synthetic PDF."""

    async def run() -> bytes:
        settings = _settings_with_concurrency()
        service = await _service(settings)
        job = await service.submit_demo()
        return export_json(await service.wait(job.id))

    _run_and_write(run(), output)


@app.command()
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
) -> None:
    """Start the local API. Use the Makefile to run API and web UI together."""
    import uvicorn

    uvicorn.run("chna_extractor.api:app", host=host, port=port, reload=False)


def _run(awaitable: Coroutine[Any, Any, None]) -> None:
    try:
        asyncio.run(awaitable)
    except ChnaError as exc:
        typer.echo(f"Error [{exc.code}]: {exc.user_message}", err=True)
        raise typer.Exit(code=1) from exc


def _run_and_write(awaitable: Coroutine[Any, Any, bytes], output: Path | None) -> None:
    try:
        payload = asyncio.run(awaitable)
    except ChnaError as exc:
        typer.echo(f"Error [{exc.code}]: {exc.user_message}", err=True)
        raise typer.Exit(code=1) from exc
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        typer.echo(f"Wrote {output}")
    else:
        typer.echo(payload.decode("utf-8-sig"), nl=False)
