# Security and privacy

## Defaults

- 25 MiB upload and 500-page limits; server-generated storage names and containment checks.
- PDF signature/end-marker validation, encrypted-file rejection, active-content/attachment rejection,
  and text-only parsing. Links are never followed.
- Optional OCR uses argument arrays, `shell=False`, temporary page images, and a hard timeout.
- External features and source retention are off. Credentials use `SecretStr`, stay server-side, and
  are redacted from structured logs.
- Extraction responses receive `Cache-Control: no-store`; errors are sanitized and correlated by a
  random request ID. Request-schema errors never echo submitted values.
- CSV cells neutralize `=`, `+`, `-`, and `@` formula prefixes.

## Model boundary

PDF text is explicitly delimited as untrusted. The developer instruction says to ignore document
instructions, use no outside knowledge, provide exact evidence, and emit only the schema. OpenAI
requests use `store=false`, no background mode, no tools by default, a hashed non-identifying safety
seed, timeout, no hidden SDK transport retries, and at most one schema-correction request. Each
potentially billable attempt is budget-reserved before it starts, and output tokens are explicitly
bounded. These limits are observable in the CLI estimate.

## Data lifecycle

The local `.data/` directory is gitignored. API uploads are deleted after success or failure by
default; job metadata/results remain in local SQLite. Set `CHNA_RETAIN_UPLOADED_FILES=true` only for a
controlled debugging environment. Delete `.data/` to remove all local state.

CLI outputs (`demo-result.json` and the default `chna-output/` directory) are ignored by Git and the
Docker build context. Treat any custom output location as potentially sensitive and delete or move it
to approved storage after review.

Docker Compose binds to `127.0.0.1` by default. The API has no user authentication because it is a
local portfolio demo; any shared or remote deployment requires authentication, rate limiting,
tenant isolation, durable job controls, and an explicit data-retention policy before exposure.

Before live testing, create a scoped sandbox key and cap its spend. Never reuse credentials from an
internship or legacy folder. Rotate any legacy OpenAI, Slack, Pinecone, ClickUp, HubSpot, Microsoft,
Google Maps, or Smarty credential that may have been stored in plaintext.
