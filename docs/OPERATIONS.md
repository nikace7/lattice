# Local operations

Use `pnpm run setup` followed by `pnpm dev`. Docker Desktop must use Linux containers.
The first build pulls pinned runtime images; it does not download embedding or
generation weights. Ports 4400, 5440, 6380, 8026 and 1026 must be free.

Create an account at the root page and create a workspace to become its owner.
Owners can add an existing username or send an email invitation under People &
access. Open local email at `http://localhost:8026`; Mailpit captures messages and
does not deliver to real inboxes. Invitees sign in or register with the invited
address before accepting. Forgot password is available on the sign-in screen.
Collection metadata persists in PostgreSQL; source files and page previews use
private storage. Answers are not available yet.

Recovery email requires the ingestion worker; invitations send during the owner
request and report delivery failure. For host-only development run
`uv run --project backend celery --workdir backend -A config worker --pool=solo --queues=ingestion --loglevel=info`
alongside the API, or use the complete Compose stack. Set `APP_ORIGIN` to the URL
recipients use; link origins never come from request headers. Recovery retries
SMTP failures three times; inspect ingestion-worker logs for exhausted failures.
Do not enable Celery eager mode outside tests. Browser tests use eager delivery
against Mailpit and their isolated database.

Legacy accounts created before email registration retain blank email and cannot
self-recover until an operator verifies and sets their address. New accounts
require email. Do not assign addresses without verifying mailbox ownership.
Email-change and standalone verification screens are not implemented. Expired
token metadata is retained; configure a retention policy before production use.

Host development uses ports 3000 (web) and 4412 (API), with same-origin API
forwarding through Next. Set `APP_ORIGIN=http://localhost:3000` for that profile.
Use explicit `127.0.0.1` database/Redis addresses on Windows. Browser tests reserve
4411/4412 and recreate `test_lattice_browser`; stop the host API before running
them. They do not reset the development database or Redis broker. Mailpit must
also be running; browser tests only inspect their unique synthetic recipients.

`docker compose ps` shows service status. `docker compose logs api` diagnoses API
startup, and `docker compose logs migrate` diagnoses migrations. Health endpoints
are `/health/live` and `/health/ready` through port 4400. Readiness requires the
vector extension migration and a writable private storage volume.

The API waits for migrations and Redis. Workers consume separate `ingestion` and
`answers` queues with bounded concurrency. Beat has persistent scheduler state;
there are no scheduled product tasks yet. The ingestion worker sends extraction
requests through `.data/parser` to the separate offline parser container.

For host development and browser tests, run `pnpm parser:up` as well as
`pnpm infra:up`. The parser has no network, database credentials or source-storage
mount. It runs two bounded subprocesses with a 305-second deadline, 30 seconds per
page, and a 1 GiB container limit. Rebuild it after changes to `backend/pipeline`.
On Linux, grant the host user and container UID 10001 access to the private spool
directory; do not expose it through the web server or make it world-writable.

Uploads allow PDF, DOCX or UTF-8 TXT/Markdown, 25 MiB/file, 100 PDF pages, 2 million extracted
characters and 20,000 blocks. Workspaces allow 500 sources and default to 2 GiB of
original files (`MAX_WORKSPACE_STORAGE_BYTES`); previews and failed-attempt artifacts
are additional disk usage. Encrypted PDFs are rejected. Scans/low-text pages need
review. Each document has one immutable source; indexing remains pending.

The first R3 slice adds `.docx` and `.md`. DOCX ZIP metadata is capped at 100 MiB
expanded/10,000 entries; each parsed XML part is capped at 16 MiB. DTD/entities,
encrypted ZIP entries, macros, duplicate paths and unsafe member names are rejected.
No ZIP member is extracted to disk and no external relationship is resolved.
Standard `word/document.xml` packages support body paragraphs and top-level tables.
Paragraph indices count body XML paragraphs, including empty and table paragraphs;
row/cell numbers are XML positions, not reconstructed merged-cell coordinates.
Built-in Heading1–Heading9 styles provide heading paths (labels capped at 240 characters).
Headers, footers, notes, nested tables, embedded objects and complex content produce
review warnings where detected. This is text inspection, not Word layout rendering.
Markdown keeps literal syntax and original line offsets; it never renders active HTML
or loads remote images. Apply the source-kind migration and rebuild parser/workers
before using the new formats.

R3 OCR uses the parser-only image target with English/Nepali Tesseract language packs.
Apply document migration `0003` and rebuild parser/API/workers together before using
the OCR review flow. Choose English, Nepali or English + Nepali at upload; the choice
is immutable for this source. Pages with fewer than 20 native non-whitespace characters
use OCR at up to 150 DPI (4 million pixels). Each page shares a 30-second deadline
across extraction, rendering and OCR. TSV output is limited to 8 MiB; total previews
remain limited to 25 MiB. OCR confidence is an engine score, not measured accuracy.
The extraction records engine version, language, confidence and per-page status.

Owners/curators with current contribution access can accept reviewed PDF extraction.
They must exclude every failed/empty page, retain some extracted text, and provide
a review note. Acceptance checks the document revision and stores reviewer/time,
exclusions and reason. All original pages remain inspectable. `REVIEWED` means
review accepted; it does not mean indexed or searchable. Future indexing must omit
excluded pages. Existing extractions without page reports require a new upload.
DOCX warnings still require inspection; PDF page acceptance does not apply to DOCX.

The source viewer reports queued, extracting, extracted, needs-review, reviewed or failed.
Retry transient failures after restoring the parser/broker; jobs stuck for ten
minutes can be retried. Attempt IDs prevent old workers publishing after a retry.
Requests normally remove their temporary spool directory on completion. Worker
crashes can leave spool data, and failed attempts can leave private previews;
automated reconciliation, replacement and retention belong to the lifecycle phase.
Treat spool data as confidential and stop workers/parser before manual cleanup.

`pnpm infra:down` retains all data. There is deliberately no destructive reset
command. Do not remove volumes to fix a migration or credential mismatch. If `.env`
is lost after PostgreSQL was initialized, restore the prior credentials or perform
an intentional database credential rotation; setup cannot rotate a persisted DB.

The local data stores are `lattice_postgres`, `lattice_redis`, `lattice_storage`,
`lattice_models`, and `lattice_beat`. Host `.data` is separate. Backups/restore and
deletion-retention policy must be implemented and verified before storing real
documents; no backup retention or purge guarantees are claimed at initialization.

Optional Ollama: `docker compose --profile local-models up -d ollama`. The service
has no published host port and no preinstalled models. A future explicit model
preparation command must pin E5 revision/Qwen digest and record licenses, hardware,
disk use and measured behavior. There is no automatic cloud or fixture fallback.

Dependency updates: use pnpm for JS and `uv add`/`uv lock` for Python, review both
lockfiles, then run `pnpm verify` and `pnpm test:e2e`. The Next.js lint CLI is run
separately because [Next.js 16 builds do not run lint](https://nextjs.org/docs/app/api-reference/config/eslint).
Python container dependencies use [uv's locked sync](https://docs.astral.sh/uv/concepts/projects/sync/).
