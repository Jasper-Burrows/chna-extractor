from __future__ import annotations

import csv
import io

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from chna_extractor.config import Settings
from chna_extractor.costs import estimate_cost, merge_usage, usage_summary
from chna_extractor.exporters import LEGACY_COLUMNS, export_json, export_legacy_csv
from chna_extractor.models import (
    ExtractionResult,
    FieldEvidence,
    HospitalRecord,
    SourceCitation,
    UsageSummary,
)
from chna_extractor.pdf import EvidenceMethod, PageText, PdfContent


def test_record_normalizes_and_deduplicates_lists() -> None:
    record = HospitalRecord(
        hospital_name=" Example Hospital ",
        report_year=2025,
        health_priorities=[" Behavioral   health ", "behavioral health", "Access"],
        assessment_methodologies=["Survey", " survey "],
    )
    assert record.hospital_name == "Example Hospital"
    assert record.health_priorities == ["Behavioral health", "Access"]
    assert record.assessment_methodologies == ["Survey"]


@pytest.mark.parametrize("year", [1989, 2101])
def test_record_rejects_out_of_range_year(year: int) -> None:
    with pytest.raises(ValidationError):
        HospitalRecord(hospital_name="Synthetic", report_year=year)


def test_evidence_and_citations_require_safe_values() -> None:
    evidence = FieldEvidence(
        page=1, excerpt="Exact text", confidence=0.8, method=EvidenceMethod.DOCUMENT_TEXT
    )
    assert evidence.page == 1
    SourceCitation(url="https://example.com/source", title="Public source")
    with pytest.raises(ValidationError):
        SourceCitation(url="http://example.com/source", title="Insecure source")


def test_cost_estimate_and_realized_usage(settings: Settings) -> None:
    content = PdfContent(
        pages=(PageText(1, "x" * 4_000, EvidenceMethod.DOCUMENT_TEXT),),
        page_count=1,
        character_count=4_000,
        used_ocr=False,
    )
    estimate = estimate_cost(content, settings)
    assert estimate.estimated_input_tokens == 2_000
    assert estimate.estimated_output_tokens == 2_500
    assert estimate.estimated_cost_usd == pytest.approx(0.0425)
    assert estimate.expected_api_calls == 1
    assert estimate.worst_case_api_calls == 2
    assert estimate.worst_case_cost_usd == pytest.approx(0.085)

    first = usage_summary(
        input_tokens=1_000,
        cached_input_tokens=200,
        output_tokens=100,
        latency_ms=50,
        model="test-model",
        api_calls=1,
        settings=settings,
    )
    combined = merge_usage(first, UsageSummary(output_tokens=5, api_calls=1, model="web"))
    assert combined.cached_input_tokens == 200
    assert combined.output_tokens == 105
    assert combined.api_calls == 2
    assert "web" in combined.model


def test_exports_canonical_json_and_legacy_csv(sample_record: HospitalRecord) -> None:
    result = ExtractionResult(job_id="job", source_file="synthetic.pdf", records=[sample_record])
    assert b'"hospital_name": "Synthetic General Hospital"' in export_json(result)
    rows = list(csv.DictReader(io.StringIO(export_legacy_csv(result).decode("utf-8-sig"))))
    assert list(rows[0]) == LEGACY_COLUMNS
    assert rows[0]["Health Priorities"] == "Access | Behavioral health"


@given(
    marker=st.sampled_from(["=", "+", "-", "@"]),
    suffix=st.text(alphabet=st.characters(min_codepoint=65, max_codepoint=90), max_size=20),
)
def test_csv_neutralizes_spreadsheet_formula_prefixes(marker: str, suffix: str) -> None:
    record = HospitalRecord(hospital_name=marker + suffix, report_year=2025)
    result = ExtractionResult(job_id="job", source_file="synthetic.pdf", records=[record])
    row = next(csv.DictReader(io.StringIO(export_legacy_csv(result).decode("utf-8-sig"))))
    assert row["Hospital Name"].startswith("'" + marker)
