from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from chna_extractor.api import create_app
from chna_extractor.config import Settings
from chna_extractor.errors import ExtractionFailedError, LiveModeRequiredError
from chna_extractor.models import (
    EvidenceMethod,
    ExtractionMode,
    ExtractionResult,
    HospitalRecordEdit,
    JobStatus,
    ResultEditRequest,
    UsageSummary,
)
from chna_extractor.security import SavedUpload, sha256_bytes
from chna_extractor.service import ExtractionService, _pipeline_fingerprint
from chna_extractor.storage import JobStore


async def _store(settings: Settings) -> JobStore:
    store = JobStore(settings.database_path)
    await store.initialize()
    return store


@pytest.mark.asyncio
async def test_storage_job_events_result_cache_and_edit(settings: Settings, sample_record) -> None:
    store = await _store(settings)
    job = await store.create_job(
        job_id="job-1",
        mode=ExtractionMode.OFFLINE,
        source_filename="synthetic.pdf",
        stored_path=settings.fixture_path,
        fingerprint="abc",
        extractor_key="offline:v1",
    )
    assert job.status is JobStatus.QUEUED
    await store.mark_running(job.id)
    await store.add_event(job.id, stage="text", message="Text ready", progress=40)
    result = ExtractionResult(job_id=job.id, source_file="synthetic.pdf", records=[sample_record])
    await store.complete(job.id, result)
    assert (await store.get_job(job.id)).status is JobStatus.SUCCEEDED
    assert len((await store.get_events(job.id)).items) == 3
    assert (await store.get_result(job.id)).records[0].capacity == 42

    editable = HospitalRecordEdit.model_validate(
        sample_record.model_dump(exclude={"evidence", "warnings"})
    )
    editable.capacity = 43
    edited = await store.update_result(job.id, ResultEditRequest(records=[editable]))
    assert edited.records[0].capacity == 43
    assert edited.records[0].evidence["capacity"][0].method is EvidenceMethod.USER_EDIT
    assert edited.usage == result.usage
    assert edited.completed_at == result.completed_at

    await store.put_cached("cache", result)
    assert (await store.get_cached("cache")) == result
    assert await store.is_ready()


@pytest.mark.asyncio
async def test_storage_failure_and_missing_source_resume(settings: Settings) -> None:
    store = await _store(settings)
    await store.create_job(
        job_id="missing",
        mode=ExtractionMode.OFFLINE,
        source_filename="gone.pdf",
        stored_path=settings.upload_dir / "gone.pdf",
        fingerprint="abc",
        extractor_key="offline:v1",
    )
    service = ExtractionService(settings, store)
    await service.resume_pending()
    failed = await store.get_job("missing")
    assert failed.status is JobStatus.FAILED
    assert failed.error_code == "source_missing"
    with pytest.raises(ExtractionFailedError):
        await service.wait("missing")


@pytest.mark.asyncio
async def test_service_demo_cache_and_progress(settings: Settings) -> None:
    store = await _store(settings)
    service = ExtractionService(settings, store)
    first = await service.submit_demo()
    result = await service.wait(first.id)
    assert result.records[0].hospital_name.startswith("Example County")
    assert (await store.get_job(first.id)).progress == 100
    assert {event.stage for event in (await store.get_events(first.id)).items} >= {
        "queued",
        "text",
        "complete",
    }

    second = await service.submit_demo()
    cached = await service.wait(second.id)
    assert any(warning.code == "cache_hit" for warning in cached.warnings)


@pytest.mark.asyncio
async def test_cache_isolated_by_ocr_enrichment_and_limit_policy(
    settings: Settings, monkeypatch
) -> None:
    assert _pipeline_fingerprint(settings, ExtractionMode.OFFLINE) != _pipeline_fingerprint(
        settings.model_copy(update={"enable_ocr": True}), ExtractionMode.OFFLINE
    )
    assert _pipeline_fingerprint(settings, ExtractionMode.OFFLINE) != _pipeline_fingerprint(
        settings.model_copy(update={"max_pdf_pages": settings.max_pdf_pages - 1}),
        ExtractionMode.OFFLINE,
    )

    class SyntheticMapsEnricher:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def enrich(self, record):
            updated = record.model_copy(deep=True)
            updated.latitude = 12.5
            return updated

    monkeypatch.setattr("chna_extractor.service.GoogleMapsEnricher", SyntheticMapsEnricher)
    enabled = settings.model_copy(
        update={"enable_google_maps": True, "google_maps_api_key": SecretStr("sandbox")}
    )
    enabled_store = await _store(enabled)
    enriched_service = ExtractionService(enabled, enabled_store)
    enriched = await enriched_service.wait((await enriched_service.submit_demo()).id)
    assert enriched.records[0].latitude == 12.5

    disabled_service = ExtractionService(settings, await _store(settings))
    plain = await disabled_service.wait((await disabled_service.submit_demo()).id)
    assert plain.records[0].latitude is None
    assert not any(warning.code == "cache_hit" for warning in plain.warnings)


@pytest.mark.asyncio
async def test_service_live_mode_orchestrates_and_deletes_private_copy(
    settings: Settings, make_pdf, sample_record, monkeypatch
) -> None:
    live = settings.model_copy(update={"openai_api_key": SecretStr("sandbox")})
    store = await _store(live)

    class ContractExtractor:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def extract(self, _content, _source_file):
            return [sample_record], UsageSummary(model="contract"), []

    monkeypatch.setattr("chna_extractor.service.OpenAIExtractor", ContractExtractor)
    live.upload_dir.mkdir(parents=True)
    private_copy = live.upload_dir / "private.pdf"
    private_copy.write_bytes(make_pdf().read_bytes())
    upload = SavedUpload(
        path=private_copy,
        original_filename="synthetic-live.pdf",
        fingerprint=sha256_bytes(private_copy.read_bytes()),
        size_bytes=private_copy.stat().st_size,
    )
    service = ExtractionService(live, store)
    assert service._resolve_mode(private_copy, ExtractionMode.AUTO) is ExtractionMode.LIVE
    job = await service.submit(upload, ExtractionMode.LIVE)
    result = await service.wait(job.id)
    assert result.records == [sample_record]
    assert (await store.get_job(job.id)).mode is ExtractionMode.LIVE
    assert not private_copy.exists()


@pytest.mark.asyncio
async def test_service_isolates_optional_enrichment_failure(
    settings: Settings, sample_record, monkeypatch
) -> None:
    enabled = settings.model_copy(
        update={"enable_google_maps": True, "google_maps_api_key": SecretStr("sandbox")}
    )

    class FailingEnricher:
        def __init__(self, _settings: Settings) -> None:
            pass

        async def enrich(self, _record):
            raise ValueError("synthetic provider failure")

    monkeypatch.setattr("chna_extractor.service.GoogleMapsEnricher", FailingEnricher)
    service = ExtractionService(enabled, await _store(enabled))
    records, web_usage, warnings = await service._enrich([sample_record], UsageSummary())
    assert records == [sample_record]
    assert web_usage is None
    assert warnings[0].code == "enrichment_failed"


@pytest.mark.asyncio
async def test_rejected_upload_is_cleaned_without_deleting_cli_source(
    settings: Settings, make_pdf
) -> None:
    store = await _store(settings)
    service = ExtractionService(settings, store)
    settings.upload_dir.mkdir(parents=True)
    api_copy = settings.upload_dir / "generated.pdf"
    api_copy.write_bytes(make_pdf().read_bytes())
    api_upload = SavedUpload(
        path=api_copy,
        original_filename="custom.pdf",
        fingerprint=sha256_bytes(api_copy.read_bytes()),
        size_bytes=api_copy.stat().st_size,
    )
    with pytest.raises(LiveModeRequiredError):
        await service.submit(api_upload, ExtractionMode.AUTO)
    assert not api_copy.exists()

    original = make_pdf()
    cli_upload = SavedUpload(
        path=original,
        original_filename=original.name,
        fingerprint=sha256_bytes(original.read_bytes()),
        size_bytes=original.stat().st_size,
    )
    with pytest.raises(LiveModeRequiredError):
        await service.submit(cli_upload, ExtractionMode.OFFLINE)
    assert original.exists()


def _wait_for_api_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        payload = client.get(f"/api/v1/extractions/{job_id}").json()
        if payload["status"] in {"succeeded", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_api_complete_offline_journey(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        assert client.get("/readyz").status_code == 200
        config = client.get("/api/v1/config").json()
        assert config["offline_demo_available"] is True
        assert config["live_available"] is False

        created = client.post("/api/v1/extractions/demo")
        assert created.status_code == 202
        job_id = created.json()["id"]
        assert _wait_for_api_job(client, job_id)["status"] == "succeeded"
        result_response = client.get(f"/api/v1/extractions/{job_id}/result")
        assert result_response.headers["cache-control"] == "no-store"
        result = result_response.json()
        assert result["records"][0]["capacity"] == 128
        assert client.get(f"/api/v1/extractions/{job_id}/events").json()["items"]

        editable = {
            key: value
            for key, value in result["records"][0].items()
            if key not in {"evidence", "warnings"}
        }
        editable["capacity"] = 129
        updated = client.patch(f"/api/v1/extractions/{job_id}/result", json={"records": [editable]})
        assert updated.status_code == 200
        assert updated.json()["records"][0]["capacity"] == 129
        edited_payload = updated.json()
        assert edited_payload["usage"] == result["usage"]
        assert edited_payload["completed_at"] == result["completed_at"]
        assert edited_payload["records"][0]["evidence"]["capacity"] == [
            {
                "page": None,
                "excerpt": "Value replaced during human review; verify it independently.",
                "confidence": 0.0,
                "method": "user_edit",
                "source_url": None,
                "source_title": None,
            }
        ]

        malicious = client.patch(
            f"/api/v1/extractions/{job_id}/result",
            json={
                "records": [editable],
                "usage": {"estimated_cost_usd": 0},
                "source_file": "forged.pdf",
            },
        )
        assert malicious.status_code == 422
        assert malicious.json()["code"] == "invalid_request"
        assert "forged.pdf" not in malicious.text

        json_export = client.get(f"/api/v1/extractions/{job_id}/export?format=json")
        csv_export = client.get(f"/api/v1/extractions/{job_id}/export?format=csv")
        assert json_export.headers["content-type"].startswith("application/json")
        assert json_export.json()["records"][0]["evidence"]["capacity"][0]["method"] == "user_edit"
        assert "Hospital Name" in csv_export.text
        assert client.get("/missing").headers["x-content-type-options"] == "nosniff"


def test_api_rejects_arbitrary_offline_upload_without_orphan(settings: Settings, make_pdf) -> None:
    data = make_pdf().read_bytes()
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/extractions",
            files={"file": ("custom.pdf", data, "application/pdf")},
            data={"mode": "auto"},
        )
        assert response.status_code == 422
        assert response.json()["code"] == "openai_key_required"
        assert list(settings.upload_dir.glob("*.pdf")) == []

        invalid = client.post(
            "/api/v1/extractions",
            files={"file": ("custom.pdf", b"not pdf", "application/pdf")},
            data={"mode": "auto"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "invalid_pdf"


def test_production_frontend_is_served_without_shadowing_api(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend = tmp_path / "container" / "app" / "web" / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text(
        '<!doctype html><script src="/assets/app.js"></script>', encoding="utf-8"
    )
    (frontend / "mark.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets / "app.js").write_text("document.body.dataset.ready='true'", encoding="utf-8")
    monkeypatch.setenv("CHNA_FRONTEND_DIST", str(frontend))
    configured = Settings(
        _env_file=None,
        database_path=settings.database_path,
        upload_dir=settings.upload_dir,
    )
    assert configured.frontend_dist == frontend

    with TestClient(create_app(configured)) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert root.headers["content-type"].startswith("text/html")
        assert "/assets/app.js" in root.text
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/mark.svg").headers["content-type"].startswith("image/svg+xml")
        assert client.get("/healthz").json()["status"] == "ok"
        assert client.get("/docs").status_code == 200


def test_frontend_root_has_safe_api_fallback_when_dist_is_absent(
    settings: Settings, tmp_path: Path
) -> None:
    configured = settings.model_copy(update={"frontend_dist": tmp_path / "missing-dist"})
    with TestClient(create_app(configured)) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert root.json() == {
            "name": "CHNA Extractor",
            "docs": "/docs",
            "health": "/healthz",
        }
        assert client.get("/mark.svg").status_code == 404
        assert client.get("/healthz").json()["status"] == "ok"
