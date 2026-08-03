from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from chna_extractor.batch import BatchCheckpoint, run_batch
from chna_extractor.cli import app
from chna_extractor.config import Settings
from chna_extractor.errors import BudgetExceededError
from chna_extractor.models import ExtractionMode
from chna_extractor.service import ExtractionService
from chna_extractor.storage import JobStore


@pytest.mark.asyncio
async def test_batch_checkpoint_resume(settings: Settings, tmp_path: Path) -> None:
    source = tmp_path / "reports"
    source.mkdir()
    fixture_copy = source / "public-synthetic.pdf"
    shutil.copyfile(settings.fixture_path, fixture_copy)
    output = tmp_path / "output"
    checkpoint_path = output / ".checkpoint.json"
    store = JobStore(settings.database_path)
    await store.initialize()
    service = ExtractionService(settings, store)

    state = await run_batch(
        files=[fixture_copy],
        output_dir=output,
        checkpoint_path=checkpoint_path,
        mode=ExtractionMode.AUTO,
        output_format="json",
        service=service,
    )
    assert len(state.completed) == 1
    assert (output / "public-synthetic.json").exists()
    assert BatchCheckpoint.load(checkpoint_path) == state

    # A second run sees both checkpoint and output and performs no duplicate work.
    second = await run_batch(
        files=[fixture_copy],
        output_dir=output,
        checkpoint_path=checkpoint_path,
        mode=ExtractionMode.AUTO,
        output_format="json",
        service=service,
    )
    assert second == state


@pytest.mark.asyncio
async def test_batch_preserves_recursive_paths_and_deduplicates_content(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "reports"
    first = source / "north" / "report.pdf"
    second = source / "south" / "report.pdf"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    shutil.copyfile(settings.fixture_path, first)
    shutil.copyfile(settings.fixture_path, second)
    output = tmp_path / "output"
    store = JobStore(settings.database_path)
    await store.initialize()
    service = ExtractionService(settings, store)
    original_submit = service.submit
    submit_calls = 0

    async def counted_submit(*args, **kwargs):
        nonlocal submit_calls
        submit_calls += 1
        return await original_submit(*args, **kwargs)

    monkeypatch.setattr(service, "submit", counted_submit)
    state = await run_batch(
        files=[first, second],
        source_root=source,
        output_dir=output,
        checkpoint_path=output / ".checkpoint.json",
        mode=ExtractionMode.AUTO,
        output_format="json",
        service=service,
    )
    assert submit_calls == 1
    assert len(state.completed) == 2
    assert (output / "north" / "report.json").exists()
    assert (output / "south" / "report.json").exists()


@pytest.mark.asyncio
async def test_batch_malformed_pdf_does_not_cancel_valid_work(
    settings: Settings, tmp_path: Path
) -> None:
    source = tmp_path / "reports"
    source.mkdir()
    valid = source / "valid.pdf"
    malformed = source / "malformed.pdf"
    shutil.copyfile(settings.fixture_path, valid)
    malformed.write_bytes(b"not-a-pdf")
    output = tmp_path / "output"
    store = JobStore(settings.database_path)
    await store.initialize()
    service = ExtractionService(settings, store)
    first = await run_batch(
        files=[valid, malformed],
        source_root=source,
        output_dir=output,
        checkpoint_path=output / ".checkpoint.json",
        mode=ExtractionMode.AUTO,
        output_format="json",
        service=service,
    )
    assert len(first.completed) == 1
    assert len(first.failed) == 1
    assert (output / "valid.json").exists()
    second = await run_batch(
        files=[valid, malformed],
        source_root=source,
        output_dir=output,
        checkpoint_path=output / ".checkpoint.json",
        mode=ExtractionMode.AUTO,
        output_format="json",
        service=service,
    )
    assert second == first


@pytest.mark.asyncio
async def test_live_batch_refuses_aggregate_worst_case_over_budget(
    settings: Settings, make_pdf, tmp_path: Path, monkeypatch
) -> None:
    first = make_pdf(text="Distinct live report alpha " * 20)
    second = make_pdf(text="Distinct live report beta " * 20)
    live = settings.model_copy(
        update={"openai_api_key": SecretStr("sandbox"), "total_budget_usd": 0.1}
    )
    store = JobStore(live.database_path)
    await store.initialize()
    service = ExtractionService(live, store)
    submit_calls = 0

    async def should_not_submit(*_args, **_kwargs):
        nonlocal submit_calls
        submit_calls += 1
        raise AssertionError("aggregate preflight must run before submission")

    monkeypatch.setattr(service, "submit", should_not_submit)
    with pytest.raises(BudgetExceededError, match="estimated request cost"):
        await run_batch(
            files=[first, second],
            output_dir=tmp_path / "output",
            checkpoint_path=tmp_path / "output" / ".checkpoint.json",
            mode=ExtractionMode.LIVE,
            output_format="json",
            service=service,
        )
    assert submit_calls == 0


def test_cli_demo_and_estimate_use_public_fixture(tmp_path: Path, settings: Settings) -> None:
    runner = CliRunner()
    environment = {
        "CHNA_DATABASE_PATH": str(tmp_path / "cli.db"),
        "CHNA_UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    output = tmp_path / "demo.json"
    demo = runner.invoke(app, ["demo", "--output", str(output)], env=environment)
    assert demo.exit_code == 0, demo.output
    assert json.loads(output.read_text())["records"][0]["report_year"] == 2025

    estimate = runner.invoke(app, ["estimate", str(settings.fixture_path)], env=environment)
    assert estimate.exit_code == 0, estimate.output
    estimate_payload = json.loads(estimate.output)
    assert estimate_payload["expected_api_calls"] == 1
    assert estimate_payload["worst_case_api_calls"] == 2
    assert estimate_payload["worst_case_cost_usd"] >= estimate_payload["estimated_cost_usd"]


def test_cli_reports_missing_pdfs(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["batch", str(tmp_path)])
    assert result.exit_code == 1
    assert "No PDF files found" in result.output
