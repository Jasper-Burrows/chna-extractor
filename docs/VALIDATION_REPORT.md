# Local validation report

Validated on 2026-08-03 with Python 3.13.9 and Node.js 24.14.0. The repository targets the Python
3.13 and Node.js 24 runtime lines; exact application dependencies are captured in `uv.lock` and
`web/package-lock.json`.

## Acceptance results

| Gate | Result |
|---|---|
| Ruff format and lint | Passed, zero findings |
| Strict mypy | Passed across 17 source files |
| Pytest | 47 passed, 1 opt-in live test skipped |
| Backend branch coverage | 90.93% overall; core models, security, service, storage, extraction, cost, and export modules meet their targets |
| `uv.lock` consistency | Passed offline; 64 packages resolved |
| Frontend TypeScript and ESLint | Passed, zero findings/warnings |
| Vitest and accessibility | 3 passed, including an axe audit |
| Production frontend build | Passed; 70 modules, 78.52 kB gzipped JavaScript and 7.14 kB gzipped CSS |
| Playwright | 3 passed on the complete pre-hardening build: mocked desktop, mocked Pixel 7, and real FastAPI offline journey; final local-listen rerun was blocked by the execution platform's approval quota |
| Locked Python dependency audit | No known vulnerabilities found |
| npm dependency audit | 0 vulnerabilities found |
| Fresh wheel/source build | Pending: the post-hardening `uv build --offline --no-sources` request was rejected after the execution platform exhausted its approval quota; the ignored root `dist/` artifacts predate hardening and must not be published |

The real-backend browser journey starts FastAPI and Vite, submits the bundled synthetic report,
opens page evidence, edits and persists the hospital name, then reads the downloaded canonical JSON
and legacy-compatible CSV. Backend acceptance tests additionally cover static production-SPA
serving from an environment-configured non-editable/container path, the missing-build API fallback,
malformed/empty/active/oversized PDFs, upload cleanup, fabricated/out-of-range/missing evidence,
duplicate hospitals, multi-hospital page evidence, per-attempt and aggregate budget bounds,
cross-policy cache isolation, recursive batch collisions, partial batch failures, narrow review edits,
restart resume, checkpoints, and formula-safe exports.

## Security, data, and dependency review

- A manual repository scan found no provider-token, private-key, or known credential patterns. The
  only employer name in source-controlled content is the intended public-safe README attribution.
- All included records, evidence, screenshots, and the bundled PDF are synthetic. No historical
  caches, PDFs, outputs, logs, virtual environments, internal URLs, or employer configuration are
  intended for version control; generated paths are covered by `.gitignore` and `.dockerignore`.
- No project license is granted. Dependencies retain their own terms. PyMuPDF is dual
  AGPL/commercial licensed; see `THIRD_PARTY_NOTICES.md`.
- CI includes Gitleaks, CodeQL, locked Python and npm audits, backend/frontend/browser gates, and a
  container build with a Tesseract smoke check. Dependabot is configured for Python,
  npm, Docker, and GitHub Actions.

## Verification boundaries

| Integration | Status | Reason |
|---|---|---|
| Synthetic PDF, offline extractor, SQLite, API, CLI | Offline verified | Executed locally through unit, integration, and API tests |
| React offline demo through FastAPI | Previously offline verified; final rerun pending | The full journey passed 3/3 before the final narrow edit-contract hardening. Final TypeScript, unit, build, and backend API journeys passed; the execution platform rejected the local-listen rerun after its approval quota was exhausted |
| OpenAI Responses extraction | Contract verified | Structured request/response, timeout, retry, privacy, and error contracts tested; no fresh sandbox key supplied |
| OpenAI web-search fallback | Contract verified | Bounded source-linked fallback tested with synthetic responses; disabled by default |
| Google Maps enrichment | Contract verified | HTTP adapter behavior tested with synthetic responses; disabled by default |
| Tesseract OCR | Contract verified locally; container smoke configured | Success, unavailable-binary, and timeout paths tested; the image installs Tesseract and CI executes `tesseract --version`, but neither Tesseract nor Docker was installed locally |
| Container image | CI configured, not locally verified | Docker was not installed locally; CI builds the image and asserts Tesseract is present |
| Python wheel/source artifacts | Source verified; artifact rebuild pending | Rebuild after the platform approval limit is cleared, then inspect the new wheel/sdist before attaching either to a release |

No live provider call was made and no legacy credential was read or used. Before live validation,
rotate every relevant historical credential, use newly issued sandbox credentials, review the
estimate, and retain the default US$10 total OpenAI budget cap. No GitHub repository, remote, branch,
pull request, release, or visibility change was created during this validation.
