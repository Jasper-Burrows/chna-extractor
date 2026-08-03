"""Public domain models shared by the API, CLI, storage, and extractors."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExtractionMode(StrEnum):
    AUTO = "auto"
    OFFLINE = "offline"
    LIVE = "live"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvidenceMethod(StrEnum):
    DOCUMENT_TEXT = "document_text"
    OCR = "ocr"
    MODEL = "model"
    ENRICHMENT = "enrichment"
    USER_EDIT = "user_edit"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class UrbanRural(StrEnum):
    URBAN = "urban"
    RURAL = "rural"
    SUBURBAN = "suburban"
    UNKNOWN = "unknown"


class FieldEvidence(StrictModel):
    page: Annotated[int, Field(ge=1)] | None
    excerpt: Annotated[str, Field(min_length=1, max_length=500)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    method: EvidenceMethod = EvidenceMethod.DOCUMENT_TEXT
    source_url: Annotated[str, Field(pattern=r"^https://", max_length=2_048)] | None = None
    source_title: Annotated[str, Field(max_length=300)] | None = None


class SourceCitation(StrictModel):
    url: AnyHttpUrl
    title: Annotated[str, Field(min_length=1, max_length=300)]

    @field_validator("url")
    @classmethod
    def require_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https":
            raise ValueError("citation URLs must use HTTPS")
        return value


class ExtractionWarning(StrictModel):
    code: Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]
    message: Annotated[str, Field(min_length=1, max_length=500)]
    severity: WarningSeverity = WarningSeverity.WARNING
    field: str | None = None


class UsageSummary(StrictModel):
    input_tokens: Annotated[int, Field(ge=0)] = 0
    cached_input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    latency_ms: Annotated[int, Field(ge=0)] = 0
    estimated_cost_usd: Annotated[float, Field(ge=0)] = 0
    model: str = "offline-deterministic"
    api_calls: Annotated[int, Field(ge=0)] = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class HospitalRecord(StrictModel):
    hospital_name: Annotated[str, Field(min_length=1, max_length=300)]
    hospital_system: str | None = None
    report_year: Annotated[int, Field(ge=1990, le=2100)]
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    capacity: Annotated[int, Field(ge=0)] | None = None
    urban_rural: UrbanRural = UrbanRural.UNKNOWN
    health_priorities: list[str] = Field(default_factory=list, max_length=50)
    assessment_methodologies: list[str] = Field(default_factory=list, max_length=50)
    evidence: dict[str, list[FieldEvidence]] = Field(default_factory=dict)
    warnings: list[ExtractionWarning] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_lists(self) -> Self:
        self.health_priorities = _deduplicate(self.health_priorities)
        self.assessment_methodologies = _deduplicate(self.assessment_methodologies)
        return self


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = " ".join(raw.split())
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


class ExtractionPayload(StrictModel):
    """Schema requested from the model before local metadata is added."""

    records: Annotated[list[HospitalRecord], Field(min_length=1, max_length=50)]


class ExtractionResult(StrictModel):
    job_id: str
    source_file: str
    records: Annotated[list[HospitalRecord], Field(min_length=1, max_length=50)]
    usage: UsageSummary = Field(default_factory=UsageSummary)
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=utc_now)


class HospitalRecordEdit(StrictModel):
    """Only human-reviewable values; model provenance is intentionally absent."""

    hospital_name: Annotated[str, Field(min_length=1, max_length=300)]
    hospital_system: str | None
    report_year: Annotated[int, Field(ge=1990, le=2100)]
    address: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None
    capacity: Annotated[int, Field(ge=0)] | None
    urban_rural: UrbanRural
    health_priorities: list[str] = Field(max_length=50)
    assessment_methodologies: list[str] = Field(max_length=50)

    @model_validator(mode="after")
    def normalize_lists(self) -> Self:
        self.health_priorities = _deduplicate(self.health_priorities)
        self.assessment_methodologies = _deduplicate(self.assessment_methodologies)
        return self


class ResultEditRequest(StrictModel):
    records: Annotated[list[HospitalRecordEdit], Field(min_length=1, max_length=50)]


class CostEstimate(StrictModel):
    page_count: Annotated[int, Field(ge=0)]
    character_count: Annotated[int, Field(ge=0)]
    estimated_input_tokens: Annotated[int, Field(ge=0)]
    estimated_output_tokens: Annotated[int, Field(ge=0)]
    expected_api_calls: Annotated[int, Field(ge=1)]
    worst_case_api_calls: Annotated[int, Field(ge=1)]
    estimated_cost_usd: Annotated[float, Field(ge=0)]
    worst_case_cost_usd: Annotated[float, Field(ge=0)]
    model: str
    assumptions: list[str]


class ProgressEvent(StrictModel):
    sequence: Annotated[int, Field(ge=1)]
    stage: str
    message: str
    progress: Annotated[int, Field(ge=0, le=100)]
    created_at: datetime = Field(default_factory=utc_now)


class ProgressEvents(StrictModel):
    items: list[ProgressEvent]


class JobResponse(StrictModel):
    id: str
    status: JobStatus
    progress: Annotated[int, Field(ge=0, le=100)]
    message: str
    mode: ExtractionMode
    source_filename: str
    created_at: datetime
    updated_at: datetime
    error_code: str | None = None
    links: dict[str, str] = Field(default_factory=dict)


class ApiConfig(StrictModel):
    offline_demo_available: bool
    live_available: bool
    max_upload_mb: int
    model: str
    optional_features: dict[str, bool]


class HealthResponse(StrictModel):
    status: str
    version: str


class ApiError(StrictModel):
    error: str
    code: str
    request_id: str | None = None
    details: dict[str, Any] | None = None
