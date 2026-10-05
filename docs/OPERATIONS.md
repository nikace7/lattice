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
`answers` queues with bounded concurrency. Beat schedules extraction recovery every
30 seconds on the ingestion queue. Run one beat instance. The ingestion worker sends extraction
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
review accepted; it does not mean indexed or searchable. Indexing omits
excluded pages. Existing extractions without page reports require a new upload.
DOCX warnings require inspection and a review note accepting the listed omissions;
page exclusions are rejected for Word documents.

The source viewer reports queued, extracting, extracted, needs-review, reviewed,
cancelled or failed. Apply migration `0004` and restart API/workers/beat/parser
together before using cancellation/recovery. Owners/curators with current contribution
access can cancel queued/extracting work. Cancellation preserves the original and
immediately prevents publication; a live worker notices within its next one-second
poll, removes its spool and the supervisor terminates that job's process group.
Cancellation after publication returns a conflict and preserves the extraction.

Workers renew their database lease every 15 seconds while awaiting the parser;
90 seconds without an update expires it. Beat recovery checks up to 100 expired
queued/extracting jobs per run, rechecks uploader access and rotates attempt IDs
before requeueing. After three automatic recoveries it records a retryable failure.
Cancelled and terminal jobs are not automatically requeued. Retry transient failures
after restoring the parser/broker; manual retry also handles cancelled or expired
jobs and resets the recovery budget. The API supplies current retry eligibility.
Attempt/state/lease checks prevent cancelled, expired or replaced workers publishing.
Broker, worker and beat must be running for automatic recovery; manual retry remains
available without beat. Queue loss is recovered from the durable queued database row.
Requests normally remove their temporary spool directory on completion. Worker
crashes can leave spool data, and failed attempts can leave private previews;
an orphaned parser still has its 305-second process deadline. Automated artifact
cleanup, replacement and retention belong to the lifecycle phase.
Treat spool data as confidential and stop workers/parser before manual cleanup.

`pnpm infra:down` retains all data. There is deliberately no destructive reset
command. Do not remove volumes to fix a migration or credential mismatch. If `.env`
is lost after PostgreSQL was initialized, restore the prior credentials or perform
an intentional database credential rotation; setup cannot rotate a persisted DB.

The local data stores are `lattice_postgres`, `lattice_redis`, `lattice_storage`,
`lattice_models`, and `lattice_beat`. Host `.data` is separate. Backups/restore and
deletion-retention policy must be implemented and verified before storing real
documents; no backup retention or purge guarantees are claimed at initialization.

### Local indexing

Apply document migration `0005`, then rebuild/restart API, ingestion-worker and beat.
The ingestion and API images install the optional `local` Python extra (CPU PyTorch
and Transformers); parser and base runtime images do not. Set `RAG_MODE=LOCAL`
for real semantic vectors, or keep `RETRIEVAL_ONLY` for explicit keyword-only indexes.
Cloud/fixture indexing is not implemented and returns a clear validation error.

Prepare model files explicitly before requesting an index:

```sh
# Host development
pnpm models:prepare
pnpm models:check
# Compose storage is separate from the host .data/models directory
docker compose run --rm --no-deps ingestion-worker python backend/manage.py prepare_models
docker compose run --rm --no-deps ingestion-worker python backend/manage.py check_models
```

E5 model/tokenizer revision is `614241f622f53c4eeff9890bdc4f31cfecc418b3` (MIT).
Preparation downloads only the pinned config/tokenizer/safetensors/model card and
records SHA-256 checksums. It does not download Ollama or send document text.
`LOCAL_EMBED_MODEL_REVISION` may be blank for the code-pinned default or match that
revision; another value fails configuration validation. Runtime checks the manifest
and file checksums, loads local safetensors with remote code disabled, and never
downloads missing files or falls back to another provider.

Open an extracted/reviewed source and select **Prepare search index**. In R3, one
immutable index/profile belongs to each extraction. Choose LOCAL before initial
indexing if semantic search is wanted: switching an existing index to another
profile requires the R6 shadow-reindex feature. No existing environment mode is
changed by setup. Ready indexes are available in Search. Generation remains future work.

Chunks target 320 and cap at 384 E5 tokens, with up to 40 tokens of overlap within
the same section. PDF pages and DOCX headings separate sections; TXT blank lines
separate paragraphs and Markdown ATX-like heading lines are conservative boundaries
(including inside literal code). Setext Markdown heading recognition is not yet
implemented. Literal source text and Python Unicode code-point spans are retained;
newlines joining blocks have no invented source span. Embedding uses `passage: `
without adding a document title, and rejects inputs over 512 tokens including prefix
and special tokens. Query embedding uses `query: `; both use masked mean pooling and
L2 normalization. Exact 384 dimensions, finite values and unit norm are validated.

Tables repeat the first row as source-backed context for each following row; this
does not claim that the first row is a semantic header. A row plus its context must
fit 384 tokens; wider/longer rows fail with an actionable message instead of dropping
cells or silently truncating. Documents are capped at 10,000 chunks. Cell-wise
packing for oversized rows remains a documented limitation.

New chunks/vectors stay inactive. Batches of at most 32 vectors commit only after
current permission, attempt and lease checks. Retry preserves completed batches,
recomputes/checks chunk hashes/spans and resumes missing vectors. Activation is one
transaction requiring every chunk and required vector. An explicit NONE profile
requires complete chunks but stores no vectors. Cancellation prevents late writes;
local inference stops at the next batch boundary. Originals and extraction survive.

Index leases renew every 15 seconds and expire after 90 seconds. Beat recovers at
most 100 expired jobs per run with fresh attempts, up to three recoveries. Manual
retry resets that budget. Processing has a 20-minute cooperative deadline and a
21-minute Celery hard limit on supported worker platforms. Use Linux workers for
production process limits. Cancelled, completed and failed jobs are not auto-requeued.
Partial artifact retention/cleanup remains part of R6.

### R4 search

Apply retrieval migration `0001`, then rebuild the API image. The API uses the
existing ingestion build target so query embeddings have the same dependencies.
Host semantic search needs `uv sync --project backend --extra local` and prepared
host model files. No runtime downloads or provider fallback occur.

Search defaults to keyword. Semantic and hybrid reject a selected scope containing
NONE or mismatched profiles; choose keyword or explicitly narrow collections.
An omitted collection list means all current readable collections; an empty list
means none. Unknown/inaccessible collection IDs are intersected out without
broadening scope. No active indexes means an empty result, without model loading.
Queries cap at 4,000 characters; semantic inputs additionally must fit 512 tokens
including the prefix and special tokens. Long inputs fail rather than truncate.

Keyword search uses PostgreSQL websearch syntax and weighted title/DOCX heading/body
vectors, with English configuration or simple configuration for Devanagari content.
This is PostgreSQL text ranking, not BM25. NFC applies to matching only; displayed
source text and offsets remain unchanged. Exact cosine and keyword ranking each
take 20 hits with chunk-ID tie breaks; equal RRF uses `1/(60+rank)`. Top 12 are
deduplicated for identical or >=90% similar overlapping text within the same source,
then up to 8 passages are selected, at most 3 per document when multiple documents
remain. Generation-token budgeting will be added with R5's generator tokenizer.
The APIs follow [Django full-text search](https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/)
and [pgvector's Django distance functions](https://github.com/pgvector/pgvector-python#django).

Search is limited to 30 requests per user per minute. One query inference runs per
API process; concurrent semantic requests get 503 and can retry. Model loading is
cached per process, with no result cache. Restart the API after replacing prepared
model artifacts. Database statements, including workspace-lock waits, cap at 10s.
Exact ranking computes vectors dynamically at this scale; measured performance
must justify stored search vectors/GIN or filtered ANN indexes later.

SearchRun retains only authorized IDs, ranks, scores, hashes, timing and effective
scope, without questions or excerpts. There is no historical-results endpoint.
Retention/purge of this metadata is future R6 work. Curator diagnostics are scoped
to their readable collections; the role does not grant access to restricted sources.

Development evaluation (run from the host repository root):

```sh
# Requires PostgreSQL and applied migrations; temporary synthetic rows roll back.
uv run --project backend --extra local python backend/manage.py evaluate_retrieval
# Explicit offline embedding check; does NOT test database/keyword/hybrid retrieval.
uv run --project backend --extra local python backend/manage.py evaluate_retrieval --embedding-only
```

The versioned 16-document/10-question development corpus reports evidence Recall@8,
any/full-evidence counts and MRR separately for English/Nepali. Canonical source
blocks use the actual chunker/tokenizer; this small check does not test parsers,
API permissions, grounding or the full R8 held-out corpus. Database mode compares
keyword/semantic/hybrid over the same temporary corpus. All model inference happens
before the temporary DB transaction. The observed offline report is in
`docs/evaluations/r4-embedding-development.json`; PostgreSQL results remain pending.

Optional Ollama: `docker compose --profile local-models up -d ollama`. The service
has no published host port and no preinstalled models. Generation/Qwen preparation
remains future work. There is no automatic cloud or fixture fallback.

Dependency updates: use pnpm for JS and `uv add`/`uv lock` for Python, review both
lockfiles, then run `pnpm verify` and `pnpm test:e2e`. The Next.js lint CLI is run
separately because [Next.js 16 builds do not run lint](https://nextjs.org/docs/app/api-reference/config/eslint).
Python container dependencies use [uv's locked sync](https://docs.astral.sh/uv/concepts/projects/sync/).
