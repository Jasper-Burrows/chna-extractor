# Testing and verification status

## Offline acceptance gates

- Backend: Ruff format/lint, strict mypy, pytest with branch coverage and 80% project threshold.
- Domain target: at least 90% for models, security, exporters, cost, and deterministic extraction.
- Frontend: ESLint, TypeScript, Vitest/Testing Library, accessibility assertions, production build.
- Journey: Playwright starts local services, runs the synthetic demo, inspects evidence, edits a field,
  and downloads JSON/CSV.
- Security: secret scan, dependency audits, CodeQL, and container build.

Synthetic cases cover text PDF, malformed/truncated/empty/encrypted/active PDFs, OCR disabled and
adapter failures, multi-record schemas, duplicate merging, fabricated/out-of-range/missing evidence,
per-attempt and aggregate budgets, pipeline-policy cache isolation, recursive filename collisions,
partial batch failure/resume, narrow review-edit provenance, bounded retry, timeout mapping, upload
paths/limits/content types, export compatibility/formula injection, and API lifecycle.

## Integration matrix

| Integration | Normal CI | Status rule |
|---|---|---|
| Synthetic PDF / offline extractor | Full execution | Offline verified after green suite |
| SQLite / API / CLI / browser journey | Full execution | Offline verified after green suite |
| OpenAI Responses | Mocked contract | Contract verified until fresh-key run |
| Tesseract OCR | Unit/adapter contract | Contract verified unless binary exercised |
| Google Maps | Mocked HTTP contract | Contract verified until fresh-key run |
| OpenAI web-search fallback | Mocked contract | Contract verified until fresh-key run |

Exact local results and environment limitations are recorded in
[VALIDATION_REPORT.md](VALIDATION_REPORT.md). A configured adapter is not evidence of a successful
live call.
