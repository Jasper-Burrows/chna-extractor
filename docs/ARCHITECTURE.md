# Architecture

The API and CLI are delivery adapters. Both pass a `SavedUpload` to `ExtractionService`, so security,
mode selection, caching, model behavior, evidence validation, enrichment, and export do not drift.

SQLite records every job transition and event. A restart schedules queued/running jobs whose private
source still exists. Successful identical inputs are copied from a schema/model-specific cache.
Uploaded copies are deleted at the terminal state unless retention is explicitly enabled; CLI source
files are never deleted.

Because cached results include optional enrichment, cache identities hash the complete result-shaping
pipeline policy: mode/schema/model, PDF and OCR limits, active Maps/web-search policy, provider-tool
limits, pricing, and budget. A result produced with enrichment or OCR enabled therefore cannot leak
into a job where those features are disabled.

The production React build is served from the typed `CHNA_FRONTEND_DIST` setting. Docker pins this to
`/app/web/dist`, so a non-editable Python installation never depends on the package's `__file__`
location to discover frontend assets. When no build is present, `/` returns a small API-discovery
response while health and documentation routes remain available.

Offline mode accepts only the exact SHA-256 fingerprint of the bundled synthetic PDF. Live mode packs
page-delimited text inside an untrusted-data boundary and requests `ExtractionPayload` through
`responses.parse`. The app sends no background request, stores no response remotely, exposes no tools
by default, and retries once only for missing/schema-invalid model output.

`HospitalRecord` is canonical. Multi-hospital reports produce multiple records. Each field can map to
one or more `FieldEvidence` values containing page, exact excerpt, confidence, and method. Result-level
warnings and `UsageSummary` make uncertainty and operating cost visible. Live output is accepted only
when evidence uses an allowed field, references a real page, and contains an excerpt found on that
page after whitespace normalization. Stable duplicate hospital identities are merged with a warning.
Human review accepts value-only records: server usage/timestamps/warnings remain authoritative, and a
changed field replaces stale model evidence with an explicit zero-confidence `user_edit` marker.

## Extension points

- `Extractor`: deterministic or OpenAI implementation.
- `RecordEnricher`: inert default or explicitly configured geocoder.
- `JobStore`: currently SQLite; service methods define the replacement boundary.
- OCR: local Tesseract subprocess with fixed arguments, page images, timeout, and no shell.
