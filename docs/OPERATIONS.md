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
private storage. Answers are available when LOCAL mode and its explicitly prepared
Qwen model are configured; the default remains retrieval-only.

The [October acceptance record](EVAL-RESULTS.md) includes actual migrations,
worker/OCR/model runs and backup restore. Private conversation downloads recheck
current access and omit entire unavailable answers. Markdown exports accept at
most 100 questions and 2 MiB; wait for any active answer to finish first. Answer
feedback is private to the conversation creator and requires an available,
completed answer. Apply conversation migration `0003` before using these controls.

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
characters and 20,000 blocks. Workspaces allow 500 documents and default to 2 GiB of
original files (`MAX_WORKSPACE_STORAGE_BYTES`); previews and failed-attempt artifacts
are additional disk usage. Encrypted PDFs are rejected. Scans/low-text pages need
review. Documents retain immutable numbered sources; only one source/index is active
for new searches. Retained originals count toward the storage quota.

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

Open an extracted/reviewed source and select **Prepare search index**. Each index
retains its immutable profile and extraction. Initial indexing chooses the configured
mode; subsequent documents use the established workspace profile. Owners can change
that profile through the R6 workspace reindex control. Setup preserves the environment
mode. Ready indexes are available in Search; generation additionally requires LOCAL
mode and prepared Qwen models.

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
R6 purge removes all artifacts for tombstoned sources; orphan source/spool directories
older than one hour are cleaned. Failed-attempt artifacts under a retained source
remain until that source is purged.

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
remain. R5's protocol additionally budgets whole passages with the generator tokenizer;
the search endpoint itself continues returning the ranked passages.
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
This metadata remains as text-free audit evidence after source purge. Curator diagnostics are scoped
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

R7 exposes this recorded synthetic development artifact to workspace owners at
`/w/:workspaceId/evaluations` and `/w/:workspaceId/evaluations/r4-embedding-development`.
The authenticated API uses the corresponding `/api/v1/workspaces/:id/evaluations`
routes. It checks active owner membership before reading fixed allowlisted files,
verifies the corpus/suite hash and recomputes comparisons from the recorded cases.
It does not read workspace documents or start inference. Expected and retrieved
evidence is canonical synthetic document text; the labels are document groups,
not exact answer spans. Citation validity, human grounding, abstention, question
latency and usage remain unmeasured. Total run duration includes model setup.

R8 adds `/w/:workspaceId/evaluations/r8-offline-semantic`, a second fixed artifact
with frozen source checksums and exact-span coverage. The reader distinguishes
development/held-out splits, versioned gold quotes and ranked chunks. Questions
without gold are labelled abstention unmeasured and excluded from the incomplete
evidence filter and answerable-rate denominators. The API validates every returned
chunk's text/span/version provenance and fixture scope, and recomputes recorded
metrics. This simulation does not validate the application's permission resolver.
See [R8 evidence](evaluations/R8.md) for reproduction, observed counts and limits.

These are fixed committed artifacts, not a general report importer or run launcher.
To update one, deliberately rerun its host command, review JSON and its versioned
corpus, then commit the new evidence. The backend image copies only the synthetic
evaluation folder from docs, evaluation fixtures and the frozen R8 source files.
Rebuild after artifact changes; existing images retain their prior report. Docker
image builds remain unverified while Docker is deferred. Demo seeding/reset and the
database-backed frozen evaluation harness still need implementation/verification.

`GET /api/v1/workspaces/:id/document-status` counts only currently readable,
nondeleted documents. Searchable and processing counts can overlap while a
replacement keeps its old active index. Processing concerns the newest source’s
queued extraction or running index. The Ask screen refreshes these counts when
opened or retried; they are a snapshot, not a live processing monitor.

Optional Ollama: `docker compose --profile local-models up -d ollama`. The service
has no published host port and no preinstalled models. Docker work is currently
deferred. There is no automatic cloud or fixture fallback.

### R5 conversations and local generation

The Ask screen creates owner-private conversations and durable answer jobs. Each
question retrieves fresh evidence; earlier answers are not model context. Generation
requires `RAG_MODE=LOCAL`, prepared E5 and Qwen artifacts, PostgreSQL migrations,
Redis, the answers worker and beat. VIEWER and retrieval-only users can read their
own existing conversations but cannot generate. The current host `.env` remains
retrieval-only. Docker and live model integration have not been validated for R5.

After Docker work resumes, apply migrations through the normal Compose startup or
`pnpm migrate` for host services. The answers worker uses the ingestion image target
for local model dependencies. Prepare models in the worker's mounted model storage;
host `.data/models` preparation does not populate the separate Compose model volume.
The commands below use public synthetic evidence and do not exercise private API
authorization, real retrieval or durable database jobs.

SSE publishes phase events and a reference to the committed, validated answer.
Reconnects replay events without rerunning generation; the client fetches the answer
through an authorized status read. Run the API under ASGI and disable proxy buffering.
Cancellation fences publication and interrupts the local HTTP request. Expired queued
jobs may be requeued three times; claimed model work is never automatically retried.
Use Ask again to create an explicitly linked new turn after a failure.

Limits are 10 questions per user per minute, 100 per workspace per UTC day, two active
jobs per workspace and one active turn per conversation. Token reservations and usage
are serialized under workspace locks. The citation reader uses the retained original
version; text highlights are exact Unicode spans, while PDF outlines show the containing
source block. Revoked source access withholds the whole stored answer.

For host development, start a separately installed local Ollama runtime, explicitly
run `ollama pull qwen3:4b`, then run `pnpm generation:prepare`. This downloads only
the pinned Qwen tokenizer and license from Hugging Face and records the digest of
the already-installed model. It never installs Ollama or pulls weights implicitly.
The default `OLLAMA_BASE_URL` is `http://localhost:11434`; only loopback or the
Compose `ollama` host is accepted, without URL credentials, paths or redirects.
An optional `OLLAMA_MODEL_DIGEST` must match the prepared manifest. Pin changes
require an explicit preparation run; runtime never silently accepts a new tag.
Host model artifacts live in gitignored `.data/models/generation`, separate from
the Compose model volume. No commands here change `.env` or `RAG_MODE`.

```sh
# Works without Ollama; downloads only the pinned tokenizer, not generation weights.
pnpm generation:prepare --tokenizer-only
pnpm generation:check --tokenizer-only
# Requires the installed/running Ollama service and an explicitly pulled qwen3:4b.
pnpm generation:prepare
pnpm generation:check
```

Tokenizer revision: `Qwen/Qwen3-4B@1cfa9a7208912126459214e8b04321603b3df60c`.
Files are checksummed and loaded locally with remote code disabled. The raw Qwen
chat template is counted before dispatch, including the non-thinking prefix.
Ollama uses a 16,384-token context, at most 10,000 input tokens per call and 3,000
output tokens per draft/repair; the verifier has 1,000 output tokens. Evidence is
at most 6,000 tokens, with whole omitted passages counted explicitly. Provider
input counts must equal the prepared tokenizer count; mismatch withholds the answer.
The API follows [Ollama's raw generation and JSON schema contract](https://docs.ollama.com/api/generate)
and [structured output guidance](https://docs.ollama.com/capabilities/structured-outputs).

At most one invalid-draft repair and one grounding pass are allowed. The total
worst-case job reservation is 37,000 tokens. The adapter records actual
input/output usage when available and retains an uncertain estimate on ambiguous
network failures; it does not retry those calls. Workers persist usage before dispatch
and reconcile the reservation on completion or lease recovery. The default daily
workspace token limit is 100,000 (`MAX_DAILY_ANSWER_TOKENS`). A generation request has a
60-second wall deadline, model inspection 10 seconds, and a protocol instance a
180-second deadline checked between calls. Closing a timed-out connection does
not prove the server stopped computation. Cancellation/access checks run at call
boundaries and during HTTP requests; lease heartbeats and final publication also
recheck the frozen access/index snapshot under the workspace lock.

New local generation usage records also contain `timings`: `requestMs` is measured
with the client's monotonic clock; `totalMs`, `loadMs`, `promptEvalMs` and
`generationMs` convert Ollama's reported nanosecond durations to milliseconds.
Missing, non-integer, negative or over-180-second runtime values remain null;
optional telemetry cannot reject an otherwise valid answer. Failed requests retain
elapsed time and their uncertain token reservation, without retrying. These fields
appear in `generation:check` output and new `review_answers` captures. Old usage
records remain valid. Request timing excludes retrieval, tokenizer initialization,
queueing before worker execution and the database writes around the model call;
retain full POST/SSE timings for end-to-end acceptance. Runtime timings are reported
measurements, not independent proof of model correctness or server cancellation.

`generation:check` prints real results for an answerable and an unsupported synthetic
question and exits unsuccessfully if they do not meet the expected statuses. It
does not establish model quality, end-to-end permissions or the R5 completion gate.
`--tokenizer-only` reports real token counts/control-token isolation and explicitly
does not run generation. Keep these results separate from model evaluations.

Dependency updates: use pnpm for JS and `uv add`/`uv lock` for Python, review both
lockfiles, then run `pnpm verify` and `pnpm test:e2e`. The Next.js lint CLI is run
separately because [Next.js 16 builds do not run lint](https://nextjs.org/docs/app/api-reference/config/eslint).
Python container dependencies use [uv's locked sync](https://docs.astral.sh/uv/concepts/projects/sync/).


## R6 source lifecycle and restore procedure

Apply the new workspace, document and conversation migrations only when resuming
PostgreSQL validation. Restart API, ingestion/answer workers and beat together;
old workers do not understand versioned source/index relations. Migration preserves
an existing uniform active workspace profile. For legacy mixed profiles, use the
owner workspace reindex control before semantic use.

Document replacement is `POST /api/v1/documents/:id/replace` (multipart file,
`uploadId`, `expectedRevision`, `ocrLanguage`). Extract, accept any warnings and
prepare the new index through existing controls. The old active source stays
searchable throughout. `GET /documents/:id/versions` is paginated;
`GET /documents/:id?sourceId=...` inspects a retained version with current access.
Search passage links resolve their active chunk's exact source, not the latest upload.

Owner `POST /workspaces/:id/reindex` accepts `profile: E5` or `NONE`; GET reads its
latest state and DELETE cancels a building batch. Every current searchable source
is included. Finish pending replacements first. Concurrent initial indexing may
change the active set and fail the batch safely; start a new batch after that work
finishes. Failure retains the working profile. Previous indexes remain retained
indefinitely; there is no automatic rollback-window expiry or index-only cleanup.
Owner `PUT /workspaces/:id/quotas` sets lower limits using the four fields returned
by GET. Storage measures original bytes across retained versions, not derived
preview/vector disk usage. Monitor the storage volume separately. Embedding calls
charge exact input counts (including prefix/special tokens) before dispatch;
uncertain outcomes retain those counts. Daily accounting uses UTC.

`POST /documents/:id/delete` requires current contribution rights and revision.
`POST /documents/:id/versions/:sourceId/purge` requires an owner and accepts only
inactive, non-latest versions. UI confirmation is explicit. Source access and
stored dependent answers become unavailable immediately; a five-minute beat task
purges at most 100 sources per batch. Retry failures and monitor oldest pending
`purge_requested_at`; 24 hours is the operational target, not a verified SLA.
Commands (purge/journal replay exercised during October acceptance):

```sh
uv run --project backend python backend/manage.py reconcile_jobs
uv run --project backend python backend/manage.py purge_documents
uv run --project backend python backend/manage.py purge_documents --reapply-tombstones
```

Deletion journals live in `STORAGE_ROOT/tombstones` and contain UUIDs only. Keep the
current journal independently backed up; never replace it with an older snapshot.
Take consistent database/source-storage backups with writes and workers stopped.
Recommended deployment backup retention is 30 days; no backup job or retention
policy is currently deployed, so operators must configure and verify expiry.
For a restore, keep API/workers stopped, restore into empty database/storage,
overlay the current tombstone journal, apply migrations, run
`purge_documents --reapply-tombstones` repeatedly until the pending-source count is
zero, then verify original checksums, citation resolution, active profiles and
access restrictions before reopening traffic. A restored source that was purged
while current in the older backup causes that restored document to be tombstoned.
Never restore a backup without the current journal. Old backups and already
exported/downloaded files may retain deleted text until their own retention expires.
This procedure remains unexecuted; successful restore consistency is still an R6 gate.

## Disposable demo commands

Follow [the demo guide](DEMO.md) to prepare ignored `.env.demo`, a separate
`lattice-demo` Compose project and the reserved `lattice_demo` database. Host
`pnpm demo:seed` imports only frozen fictional originals; Retry/review/index in
the application later. There is no default account password and no automatic
provider, email or extraction dispatch. Repeated seed preserves existing data.

Stop API, workers, beat and parser before `pnpm demo:reset --confirm lattice_demo`.
The command requires matching database/storage markers and refuses unrelated
accounts/workspaces, running jobs, a nonempty spool and links/junctions. It removes
only the marked demo's application data and dedicated source-storage content;
the database itself, installation marker, model cache and Redis remain. Never
use the demo for real documents. Interrupted operations keep a recovery state;
fix the failure and repeat guarded reset before reseeding. Do not remove/forge a
marker to bypass a refusal. A new seed uses new resource IDs.

Workspace and conversation migrations are applied on the isolated demo. Real
PostgreSQL seed/reset recovery and container execution are recorded in
[the acceptance results](EVAL-RESULTS.md). Keep normal installations migrated before
starting their upgraded API/workers.

## Frozen evaluation and answer review

[The acceptance workflow](evaluations/ACCEPTANCE.md) documents the new guarded
`run_evaluations --database` comparison and `review_answers` capture/scoring commands.
The comparison creates temporary canonical fixtures only inside a rolled-back
transaction; it never seeds an application library or dispatches jobs. Answer capture
is restricted to the matching marked demo and reads current-access delivery APIs.
Offline review accepts separate UTF-8 operator files and performs no database call.
Both SQL splits and all 80 live question attempts are now preserved separately from
the offline report. Human review templates remain blank; no human quality result
is claimed.

New demo seeds give `demo-a-member` the MEMBER role, so frozen question cases can
generate when the local model is configured. An existing READY seed is not silently
modified; use the guarded stop/reset/reseed procedure to adopt this role update.
