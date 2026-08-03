from __future__ import annotations

import csv
import io
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from chna_extractor.config import Settings
from chna_extractor.costs import estimate_cost
from chna_extractor.enrichment import (
    GoogleMapsEnricher,
    OpenAIWebSearchEnricher,
    WebEnrichmentPayload,
    WebLocation,
    _apply_web_locations,
)
from chna_extractor.errors import BudgetExceededError, LiveModeRequiredError
from chna_extractor.exporters import export_legacy_csv
from chna_extractor.extractors import (
    DemoExtractor,
    OpenAIExtractor,
    _pack_document,
    deduplicate_records,
    fixture_fingerprint,
    is_demo_fixture,
    safety_identifier,
    validate_record_evidence,
)
from chna_extractor.models import (
    ExtractionPayload,
    ExtractionResult,
    FieldEvidence,
    HospitalRecord,
    SourceCitation,
    UsageSummary,
)
from chna_extractor.pdf import EvidenceMethod, PageText, PdfContent, inspect_and_extract


def _content(
    text: str = (
        "Synthetic General Hospital Example Health 2025 1 Example Street Demo City CA 90000 "
        "42 beds Urban Access; Behavioral health Survey "
    ),
) -> PdfContent:
    return PdfContent(
        pages=(PageText(1, text, EvidenceMethod.DOCUMENT_TEXT),),
        page_count=1,
        character_count=len(text),
        used_ocr=False,
    )


@pytest.mark.asyncio
async def test_demo_extractor_is_evidence_backed(settings: Settings) -> None:
    content = inspect_and_extract(settings.fixture_path, settings)
    records, usage, warnings = await DemoExtractor().extract(content, "synthetic.pdf")
    assert records[0].hospital_name == "Example County Community Hospital"
    assert records[0].evidence["capacity"][0].page == 1
    assert usage.api_calls == 0
    assert warnings[0].code == "offline_demo"
    assert is_demo_fixture(settings.fixture_path, settings)
    assert len(fixture_fingerprint(settings)) == 64


def test_pack_document_trims_evenly_and_hashes_identifier(settings: Settings) -> None:
    content = PdfContent(
        pages=(
            PageText(1, "a" * 2_000, EvidenceMethod.DOCUMENT_TEXT),
            PageText(2, "b" * 2_000, EvidenceMethod.DOCUMENT_TEXT),
        ),
        page_count=2,
        character_count=4_000,
        used_ocr=False,
    )
    packed, warnings = _pack_document(content, max_characters=1_500)
    assert packed.startswith("<untrusted_document>")
    assert "PAGE 1" in packed and "PAGE 2" in packed
    assert warnings[0].code == "context_trimmed"
    assert len(safety_identifier(settings)) == 64
    assert safety_identifier(settings) == safety_identifier(settings)


class FakeResponses:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        output = self.outputs.pop(0)
        return SimpleNamespace(
            output_parsed=output,
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                input_tokens_details=SimpleNamespace(cached_tokens=10),
            ),
        )


class FakeOpenAIClient:
    latest: FakeOpenAIClient | None = None

    def __init__(self, *, outputs: list[object], **kwargs) -> None:
        self.init_kwargs = kwargs
        self.responses = FakeResponses(outputs)
        self.closed = False
        FakeOpenAIClient.latest = self

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_openai_extractor_uses_responses_parse_and_one_schema_retry(
    settings: Settings, sample_record: HospitalRecord, monkeypatch
) -> None:
    outputs = [None, ExtractionPayload(records=[sample_record])]

    def factory(**kwargs):
        return FakeOpenAIClient(outputs=outputs, **kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    live = settings.model_copy(
        update={
            "openai_api_key": SecretStr("new-sandbox-key"),
        }
    )
    records, usage, _ = await OpenAIExtractor(live).extract(_content(), "synthetic.pdf")
    client = FakeOpenAIClient.latest
    assert client is not None
    assert client.init_kwargs["max_retries"] == 0
    assert len(client.responses.calls) == 2
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.6-terra"
    assert call["reasoning"] == {"effort": "medium"}
    assert call["store"] is False
    assert call["max_output_tokens"] == 2_500
    assert len(str(call["safety_identifier"])) == 64
    assert records == [sample_record]
    assert usage.api_calls == 2
    assert usage.input_tokens == 200
    assert usage.output_tokens == 40
    assert usage.cached_input_tokens == 20
    assert client.closed


@pytest.mark.parametrize("failure", ["fabricated", "out_of_range", "missing", "unknown_field"])
def test_live_evidence_validation_rejects_unsupported_claims(
    sample_record: HospitalRecord, failure: str
) -> None:
    record = sample_record.model_copy(deep=True)
    if failure == "fabricated":
        record.evidence["hospital_name"][0].excerpt = "Fabricated Hospital"
    elif failure == "out_of_range":
        record.evidence["hospital_name"][0].page = 2
    elif failure == "missing":
        record.evidence.pop("hospital_name")
    else:
        record.evidence["internal_secret"] = [
            FieldEvidence(page=1, excerpt="Synthetic General Hospital", confidence=1.0)
        ]
    with pytest.raises(ValueError):
        validate_record_evidence([record], _content())


@pytest.mark.asyncio
async def test_invalid_evidence_triggers_one_schema_correction(
    settings: Settings, sample_record: HospitalRecord, monkeypatch
) -> None:
    invalid = sample_record.model_copy(deep=True)
    invalid.evidence["hospital_name"][0].excerpt = "Not in the report"
    outputs = [ExtractionPayload(records=[invalid]), ExtractionPayload(records=[sample_record])]

    def factory(**kwargs):
        return FakeOpenAIClient(outputs=outputs, **kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    live = settings.model_copy(update={"openai_api_key": SecretStr("sandbox")})
    records, usage, _ = await OpenAIExtractor(live).extract(_content(), "synthetic.pdf")
    assert records == [sample_record]
    assert usage.api_calls == 2


@pytest.mark.asyncio
async def test_schema_retry_reserves_budget_before_second_call(
    settings: Settings, monkeypatch
) -> None:
    outputs = [None, None]

    def factory(**kwargs):
        return FakeOpenAIClient(outputs=outputs, **kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    content = _content()
    per_call = estimate_cost(content, settings).estimated_cost_usd
    live = settings.model_copy(
        update={
            "openai_api_key": SecretStr("sandbox"),
            "total_budget_usd": per_call,
        }
    )
    with pytest.raises(BudgetExceededError):
        await OpenAIExtractor(live).extract(content, "synthetic.pdf")
    client = FakeOpenAIClient.latest
    assert client is not None
    assert len(client.responses.calls) == 1
    assert client.closed


@pytest.mark.asyncio
async def test_multi_hospital_structured_output_preserves_golden_evidence_pages(
    settings: Settings, monkeypatch
) -> None:
    first = HospitalRecord(
        hospital_name="Synthetic North Hospital",
        report_year=2025,
        evidence={
            "hospital_name": [
                FieldEvidence(page=1, excerpt="Synthetic North Hospital", confidence=1.0)
            ],
            "report_year": [FieldEvidence(page=1, excerpt="2025", confidence=1.0)],
        },
    )
    second = HospitalRecord(
        hospital_name="Synthetic South Hospital",
        report_year=2025,
        evidence={
            "hospital_name": [
                FieldEvidence(page=2, excerpt="Synthetic South Hospital", confidence=1.0)
            ],
            "report_year": [FieldEvidence(page=2, excerpt="2025", confidence=1.0)],
        },
    )
    outputs = [ExtractionPayload(records=[first, second])]

    def factory(**kwargs):
        return FakeOpenAIClient(outputs=outputs, **kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    live = settings.model_copy(update={"openai_api_key": SecretStr("sandbox")})
    content = PdfContent(
        pages=(
            PageText(1, "Synthetic North Hospital 2025", EvidenceMethod.DOCUMENT_TEXT),
            PageText(2, "Synthetic South Hospital 2025", EvidenceMethod.DOCUMENT_TEXT),
        ),
        page_count=2,
        character_count=59,
        used_ocr=False,
    )
    records, _, _ = await OpenAIExtractor(live).extract(content, "multi.pdf")
    assert [record.hospital_name for record in records] == [
        "Synthetic North Hospital",
        "Synthetic South Hospital",
    ]
    assert [record.evidence["hospital_name"][0].page for record in records] == [1, 2]


def test_duplicate_hospitals_merge_deterministically_with_warning(
    sample_record: HospitalRecord,
) -> None:
    duplicate = sample_record.model_copy(deep=True)
    duplicate.health_priorities.append("Nutrition")
    duplicate.evidence["health_priorities"].append(
        FieldEvidence(page=1, excerpt="Nutrition", confidence=0.9)
    )
    records, warnings = deduplicate_records([sample_record, duplicate])
    assert len(records) == 1
    assert records[0].health_priorities == ["Access", "Behavioral health", "Nutrition"]
    assert warnings[0].code == "duplicate_records_merged"
    validate_record_evidence(
        records,
        _content(_content().pages[0].text + " Nutrition"),
    )
    result = ExtractionResult(
        job_id="duplicate-golden",
        source_file="synthetic.pdf",
        records=records,
        warnings=warnings,
    )
    rows = list(csv.DictReader(io.StringIO(export_legacy_csv(result).decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["Health Priorities"].endswith("Nutrition")


@pytest.mark.asyncio
async def test_openai_extractor_requires_key_and_enforces_budget(settings: Settings) -> None:
    with pytest.raises(LiveModeRequiredError):
        OpenAIExtractor(settings)
    live = settings.model_copy(
        update={"openai_api_key": SecretStr("sandbox"), "total_budget_usd": 0.0001}
    )
    with pytest.raises(BudgetExceededError):
        await OpenAIExtractor(live).extract(_content("x" * 50_000), "large.pdf")


class FakeHttpResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"results": [{"geometry": {"location": {"lat": 1.25, "lng": 2.5}}}]}


class FakeHttpClient:
    def __init__(self, **_kwargs) -> None:
        self.params = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, _url, params):
        self.params = params
        return FakeHttpResponse()


@pytest.mark.asyncio
async def test_google_maps_adapter_is_opt_in_and_preserves_address(
    settings: Settings, sample_record: HospitalRecord, monkeypatch
) -> None:
    with pytest.raises(ValueError):
        GoogleMapsEnricher(settings)
    enabled = settings.model_copy(
        update={"enable_google_maps": True, "google_maps_api_key": SecretStr("sandbox")}
    )
    monkeypatch.setattr("chna_extractor.enrichment.httpx.AsyncClient", FakeHttpClient)
    record = await GoogleMapsEnricher(enabled).enrich(sample_record)
    assert record.latitude == 1.25
    assert record.longitude == 2.5
    assert record.evidence["latitude"][0].page is None


def test_web_locations_fill_only_missing_fields(sample_record: HospitalRecord) -> None:
    original = sample_record.model_copy(update={"address": None, "latitude": None})
    location = WebLocation(
        hospital_name=original.hospital_name,
        address="9 Public Way",
        city="Wrong City",
        state="NY",
        postal_code="10000",
        latitude=10,
        longitude=20,
        sources=[SourceCitation(url="https://example.org/hospital", title="Hospital directory")],
    )
    updated = _apply_web_locations([original], [location])[0]
    assert updated.address == "9 Public Way"
    assert updated.city == original.city
    assert updated.latitude == 10
    assert str(updated.evidence["address"][0].source_url).startswith("https://")


@pytest.mark.asyncio
async def test_web_search_adapter_contract_and_budget(
    settings: Settings, sample_record: HospitalRecord, monkeypatch
) -> None:
    location = WebLocation(
        hospital_name=sample_record.hospital_name,
        address="9 Public Way",
        city="Demo City",
        state="CA",
        postal_code="90000",
        latitude=None,
        longitude=None,
        sources=[SourceCitation(url="https://example.org/source", title="Public directory")],
    )
    outputs = [WebEnrichmentPayload(records=[location])]

    def factory(**kwargs):
        return FakeOpenAIClient(outputs=outputs, **kwargs)

    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    enabled = settings.model_copy(
        update={"enable_web_search": True, "openai_api_key": SecretStr("sandbox")}
    )
    original = sample_record.model_copy(update={"address": None})
    updated, usage, warnings = await OpenAIWebSearchEnricher(enabled).enrich(
        [original], UsageSummary()
    )
    call = FakeOpenAIClient.latest.responses.calls[0]  # type: ignore[union-attr]
    assert call["tools"] == [{"type": "web_search"}]
    assert call["max_tool_calls"] == 3
    assert call["store"] is False
    assert updated[0].address == "9 Public Way"
    assert usage is not None and usage.api_calls == 1
    assert usage.estimated_cost_usd >= enabled.web_search_reserve_usd
    assert any(warning.code == "web_search_used" for warning in warnings)

    too_small = enabled.model_copy(update={"total_budget_usd": 0.01})
    unchanged, no_usage, warnings = await OpenAIWebSearchEnricher(too_small).enrich(
        [original], UsageSummary()
    )
    assert unchanged[0].address is None
    assert no_usage is None
    assert warnings[0].code == "web_search_budget"
