"""Generate the small, public-safe PDF used by the deterministic demo and tests."""

from __future__ import annotations

from pathlib import Path

LINES = [
    "SYNTHETIC DEMONSTRATION - NOT A REAL HOSPITAL REPORT",
    "Example County Community Hospital",
    "Civic Health Collaborative (Synthetic)",
    "2025 Community Health Needs Assessment",
    "Address: 100 Example Way, Demo City, CA 90000",
    "Licensed bed capacity: 128",
    "Service area classification: Urban",
    "Priorities: Access to primary care; Behavioral health; Nutrition and physical activity",
    "Methods: Community survey; Stakeholder interviews; Secondary data review",
    "This fixture contains invented organizations, locations, and findings for testing only.",
]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf() -> bytes:
    commands = ["BT", "/F1 16 Tf", "18 TL", "72 735 Td"]
    for index, line in enumerate(LINES):
        if index:
            commands.append("T*")
        commands.append(f"({_escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n% Synthetic public fixture\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)


if __name__ == "__main__":
    destination = (
        Path(__file__).parents[1] / "src" / "chna_extractor" / "fixtures" / "synthetic_chna.pdf"
    )
    destination.write_bytes(build_pdf())
    print(f"wrote {destination} ({destination.stat().st_size} bytes)")
