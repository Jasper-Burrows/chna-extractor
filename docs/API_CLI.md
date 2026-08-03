# API and CLI reference

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/healthz`, `/readyz` | Process and database health |
| `GET` | `/api/v1/config` | Public capability flags; never secrets |
| `POST` | `/api/v1/extractions` | Multipart PDF and `auto`, `offline`, or `live` mode |
| `POST` | `/api/v1/extractions/demo` | Queue the bundled synthetic fixture |
| `GET` | `/api/v1/extractions/{id}` | Status, progress, safe message, and links |
| `GET` | `/api/v1/extractions/{id}/events` | Ordered progress events |
| `GET/PATCH` | `/api/v1/extractions/{id}/result` | Read the result or submit value-only record edits |
| `GET` | `/api/v1/extractions/{id}/export?format=json|csv` | Download export |

Uploads return `202`; poll the status link until `succeeded` or `failed`. Errors have `error`, stable
`code`, and `request_id`. Internal exception text and document contents are never returned.

The PATCH body accepts only editable hospital values under `records`. Job IDs, source filenames,
usage, timestamps, warnings, and evidence are server-owned and rejected if submitted. Changed values
replace their original page citation with an explicit zero-confidence `user_edit` provenance marker;
unchanged fields retain their extraction evidence.

## CLI

- `chna demo [-o FILE]`: keyless complete synthetic journey.
- `chna estimate PDF`: local page/text inspection with one expected call, two-call maximum, and
  expected/worst-case cost.
- `chna extract PDF [--mode MODE] [--format json|csv] [-o FILE]`.
- `chna batch DIRECTORY [--recursive] [--concurrency 1..8]`: concurrent, resumable extraction.
- `chna serve [--host 127.0.0.1] [--port 8000]`: local API.

## Legacy CSV

One row is emitted per hospital with these stable public compatibility columns: Hospital Name,
Health System, Report Year, Address, City, State, ZIP Code, Bed Capacity, Urban/Rural, Health
Priorities, Assessment Methodologies, Latitude, Longitude, and Warnings. Lists use ` | `. Values
beginning with spreadsheet formula markers are apostrophe-prefixed.

Batch mode preserves relative subdirectories so recursive same-name PDFs cannot overwrite each
other. Validation failures are checkpointed per source path without cancelling valid work, identical
content is submitted once, and live runs reserve the sum of unique files' worst-case extraction cost
before scheduling. The API cap applies independently to each submitted job; the CLI batch adds this
validation-run aggregate cap.
