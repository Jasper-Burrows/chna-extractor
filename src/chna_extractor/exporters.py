"""Canonical JSON and spreadsheet-safe legacy CSV export."""

from __future__ import annotations

import csv
import io

from chna_extractor.models import ExtractionResult, HospitalRecord

LEGACY_COLUMNS = [
    "Hospital Name",
    "Health System",
    "Report Year",
    "Address",
    "City",
    "State",
    "ZIP Code",
    "Bed Capacity",
    "Urban/Rural",
    "Health Priorities",
    "Assessment Methodologies",
    "Latitude",
    "Longitude",
    "Warnings",
]


def export_json(result: ExtractionResult) -> bytes:
    return result.model_dump_json(indent=2).encode("utf-8")


def export_legacy_csv(result: ExtractionResult) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=LEGACY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for record in result.records:
        writer.writerow(_legacy_row(record))
    return stream.getvalue().encode("utf-8-sig")


def _legacy_row(record: HospitalRecord) -> dict[str, object]:
    values: dict[str, object] = {
        "Hospital Name": record.hospital_name,
        "Health System": record.hospital_system or "",
        "Report Year": record.report_year,
        "Address": record.address or "",
        "City": record.city or "",
        "State": record.state or "",
        "ZIP Code": record.postal_code or "",
        "Bed Capacity": record.capacity if record.capacity is not None else "",
        "Urban/Rural": record.urban_rural.value,
        "Health Priorities": " | ".join(record.health_priorities),
        "Assessment Methodologies": " | ".join(record.assessment_methodologies),
        "Latitude": record.latitude if record.latitude is not None else "",
        "Longitude": record.longitude if record.longitude is not None else "",
        "Warnings": " | ".join(warning.message for warning in record.warnings),
    }
    return {key: _spreadsheet_safe(value) for key, value in values.items()}


def _spreadsheet_safe(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
