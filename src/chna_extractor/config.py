"""Typed, environment-driven configuration with secure defaults."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CHNA_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    database_path: Path = Path(".data/chna.db")
    upload_dir: Path = Path(".data/uploads")
    frontend_dist: Path = Path("web/dist")
    max_upload_mb: int = Field(default=25, ge=1, le=100)
    max_pdf_pages: int = Field(default=500, ge=1, le=2_000)
    max_concurrent_jobs: int = Field(default=2, ge=1, le=8)
    retain_uploaded_files: bool = False
    enable_ocr: bool = False
    ocr_timeout_seconds: int = Field(default=45, ge=5, le=300)

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_timeout_seconds: int = Field(default=90, ge=5, le=300)
    safety_identifier_seed: SecretStr | None = None
    input_cost_per_million: float = Field(default=2.50, ge=0)
    cached_input_cost_per_million: float = Field(default=0.25, ge=0)
    output_cost_per_million: float = Field(default=15.00, ge=0)
    total_budget_usd: float = Field(default=10.0, gt=0, le=100)

    enable_google_maps: bool = False
    google_maps_api_key: SecretStr | None = None
    enable_web_search: bool = False
    web_search_reserve_usd: float = Field(default=0.10, ge=0, le=5)
    web_search_max_records: int = Field(default=10, ge=1, le=25)
    web_search_max_tool_calls: int = Field(default=3, ge=1, le=5)

    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"

    @field_validator("openai_api_key", "google_maps_api_key", mode="before")
    @classmethod
    def empty_secret_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def live_available(self) -> bool:
        return self.openai_api_key is not None

    @property
    def fixture_path(self) -> Path:
        return Path(__file__).parent / "fixtures" / "synthetic_chna.pdf"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
