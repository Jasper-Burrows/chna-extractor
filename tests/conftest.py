from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import wrap

import fitz
import pytest

from chna_extractor.config import Settings
from chna_extractor.models import FieldEvidence, HospitalRecord, UrbanRural


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=tmp_path / "state" / "jobs.db",
        upload_dir=tmp_path / "state" / "uploads",
    )


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    counter = 0

    def create(*, text: str = "Synthetic report text " * 20, pages: int = 1) -> Path:
        nonlocal counter
        counter += 1
        path = tmp_path / f"synthetic-{counter}.pdf"
        document = fitz.open()
        for page_number in range(pages):
            page = document.new_page()
            if text:
                lines = wrap(f"{text} page {page_number + 1}", width=80)
                for line_number, line in enumerate(lines[:50]):
                    page.insert_text((50, 50 + line_number * 12), line, fontsize=9)
        document.save(path)
        document.close()
        return path

    return create


@pytest.fixture
def sample_record() -> HospitalRecord:
    def evidence(excerpt: str) -> list[FieldEvidence]:
        return [FieldEvidence(page=1, excerpt=excerpt, confidence=1.0)]

    return HospitalRecord(
        hospital_name="Synthetic General Hospital",
        hospital_system="Example Health",
        report_year=2025,
        address="1 Example Street",
        city="Demo City",
        state="CA",
        postal_code="90000",
        capacity=42,
        urban_rural=UrbanRural.URBAN,
        health_priorities=["Access", "Behavioral health"],
        assessment_methodologies=["Survey"],
        evidence={
            "hospital_name": evidence("Synthetic General Hospital"),
            "hospital_system": evidence("Example Health"),
            "report_year": evidence("2025"),
            "address": evidence("1 Example Street"),
            "city": evidence("Demo City"),
            "state": evidence("CA"),
            "postal_code": evidence("90000"),
            "capacity": evidence("42 beds"),
            "urban_rural": evidence("Urban"),
            "health_priorities": evidence("Access; Behavioral health"),
            "assessment_methodologies": evidence("Survey"),
        },
    )
