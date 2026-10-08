# Progress

## Repository initialization

Scope: initialize the existing `lattice` folder from the supplied plan. The plan's
alternate destination and full-build prompt are reference material, not a request
to create another repository or implement all eight milestones in this task.

Implemented:

- Git repository on `main`, pnpm workspace, uv backend, dependency lockfiles,
  environment example and idempotent local setup with random credentials.
- Next.js/React/TypeScript/Tailwind starter with local fonts and blueprint design tokens.
- Django/DRF/ASGI/Celery configuration, UUID user, session support, vector extension migration.
- Infrastructure health endpoints and generated OpenAPI/TypeScript contracts.
- Compose PostgreSQL/pgvector, Redis, Mailpit, Caddy, API, web, two worker queues,
  beat, a migration job, and an optional Ollama service.
- Foundation tests, formatting/lint/type/build commands and GitHub Actions verification.

R1 is implemented: accounts, workspace membership, collection authorization,
account recovery and invitations. R2 is implemented with final Docker-dependent
integration validation deferred by the user. R3 document formats, OCR/review,
chunking and local embedding/index preparation are implemented, with database/worker
integration gates still deferred and table/Markdown limitations recorded below.
R4 scoped search is implemented with PostgreSQL/browser gates deferred. R5's local
generation, private conversations, durable jobs, validated answer delivery and citation
reader are implemented; PostgreSQL/worker/browser and live model verification remain
pending. R6 lifecycle implementation is present with its PostgreSQL, worker, browser
and restore acceptance gates deferred. R7 responsive reader and owner diagnostics
are implemented. R8 frozen corpus, offline evaluation evidence and demo handoff are
present. Guarded demo tooling is implemented but unexecuted on PostgreSQL;
full-stack acceptance and the database evaluation harness stay open.
The ingestion worker handles recovery email and document
extraction; the answers queue handles private questions in LOCAL mode.

## Verification

Observed on 29 September 2026, Windows host with Node 24.20.0, pnpm 10.33.4,
uv 0.11.11, Python 3.12.13, and Docker Desktop Linux containers:

- `pnpm run setup`: passed with frozen JS dependencies and locked Python dependencies;
  existing environment preserved. Use the explicit `run`: bare `pnpm setup` is a
  reserved pnpm command, not the repository script.
- `pnpm migrate`: applied auth/content types/sessions, UUID identity, and pgvector
  extension migrations on PostgreSQL 17.
- `pnpm verify`: passed ESLint, Ruff lint/format, TypeScript, Django system checks,
  migration drift check, 1 setup test, 1 web unit test, 5 backend tests, and the
  Next.js production build. Backend tests used real PostgreSQL/pgvector and Redis.
- `pnpm test:e2e`: 3 passed, checking the production starter at 360/768/1440px,
  horizontal overflow, and axe WCAG A/AA rules. This is automated starter coverage,
  not a claim of full product WCAG compliance. Test server uses loopback port 4411
  to avoid an existing local service on the initially attempted port 3100.
- OpenAPI generation validates without warnings; regeneration produced identical
  schema and TypeScript types.
- Docker API/web images built successfully. Full Compose stack started; migration
  job exited successfully, both worker queues answered Celery ping, and the proxy
  returned HTTP 200 for the starter and readiness checks (DB/Redis/storage all true).
- Local secrets, virtualenvs, node_modules and data are ignored by Git. The original
  blueprint was preserved and its copy has an identical SHA-256 hash.

GitHub Actions is configured; local checks are the validation gate for this work.
The repository has since been pushed to the private `nikace7/lattice` remote. The optional
Ollama profile and any model download/inference remain untested and uninstalled.
No RAG quality, performance or live generation result is claimed.

## Workspace foundation — 30 September 2026

- Registration, login/logout, session bootstrap and session rotation, anonymous
  CSRF protection, password validation and Redis-backed authentication throttling.
- UUID workspaces, memberships, collections, grants and mutation audit metadata.
  Owner/curator/member/viewer role ceilings, active membership checks, restricted
  collection scope before pagination, atomic revocation and access epoch updates.
- Revision conflicts return 409. Workspace row locks serialize access changes;
  concurrent attempts to remove the final owners leave one owner active.
- Responsive library UI with account entry, workspace chooser, collection creation
  and details, owner membership management and collection grants. Empty/loading/
  error states use real API data; there are no simulated documents or answers.
- Typed OpenAPI contracts cover implemented endpoints. Host Next.js forwards API
  calls to port 4412. Explicit loopback database/Redis URLs avoid Windows IPv6
  fallback delays observed during browser testing.

Validation: `pnpm verify`, contract generation and the four Playwright tests cover
the foundation plus this slice. Backend coverage now has 14 tests, including tenant
isolation, real CSRF/session behavior and simultaneous owner demotions. Browser
coverage exercises actual Django requests and grant revocation in a second account;
axe and overflow checks run at 360/768/1440px. Compose rebuild and health checks
also passed. Automated accessibility checks do not establish full WCAG compliance.

The foundation and workspace feature were committed and merged into `main` at
`36e6729`, then pushed at the user's request. Remote CI was not a gate.

## Account recovery and invitations — 1 October 2026

- Registration now requires a normalized, case-insensitively unique email address.
  Existing accounts with blank email still sign in; recovery needs an operator to
  associate a verified address with those legacy accounts.
- Password recovery queues every syntactically valid email without a request-time
  account lookup. Celery delivers through Mailpit with bounded retries and a
  per-account cooldown. Reset links expire after 30 minutes, are stored only as
  SHA-256 digests, and are consumed under a user lock. Changing the password
  invalidates other reset links and all prior authenticated sessions.
- Owners send, replace, list and revoke invitations. Links expire in two days;
  acceptance requires a matching signed-in email and an inviter who is still an
  active owner. Workspace locking prevents replay or implicit reactivation of a
  deactivated membership. Access epochs and audit records update on acceptance.
- Recovery/reset/invitation screens use the existing reading-room design. Secrets
  travel in email URL fragments, are removed from the visible URL after capture,
  and are submitted only in CSRF-protected POST bodies. API validation messages
  now preserve non-field errors such as expired links.

The next phase after R1 is R2 PDF/TXT upload, bounded extraction and source inspection.
Retrieval, generation and production email delivery remain future work.

Validation: `pnpm verify` passed lint, formatting, types, migration checks,
24 PostgreSQL backend tests, the setup/unit tests and production build. All five
Playwright tests passed, including invitation signup/replay, recovery, old-session
invalidation and mobile recovery accessibility. Contract generation completed
without warnings. Compose rebuilt and applied the migration successfully; a
synthetic account completed recovery through the real API, Redis, Celery worker
and Mailpit, then signed in with the changed password. Final review additionally
verified that revoking an already consumed invitation returns a conflict rather
than implying that the resulting membership was removed.

## R2 document sources — 2 October 2026

- Private PDF/UTF-8 TXT upload, immutable original hashes, idempotent upload IDs,
  workspace quotas, scoped document/source APIs and revision-checked retries.
- Native PDF extraction with physical pages and normalized bounding boxes; TXT
  line/Unicode offsets and identity span maps preserve Nepali and combining marks.
- Offline, non-root parser container with bounded subprocesses, no network or
  application credentials, read-only root and validated output. Low-text pages
  require review; encrypted PDFs are rejected, including empty-password encryption.
- Responsive source reader, PNG page previews, passage selection/highlights,
  mobile focus return, original downloads, progress and actionable failure states.
- Current access is checked for source reads and again before extraction publication.
  Attempt IDs prevent stale/duplicate tasks from publishing after retries.

Completed locally: lint, Ruff formatting, TypeScript, OpenAPI generation, setup and
web unit tests, production web build, standalone native/encrypted PDF and Unicode
parser checks. Docker images built successfully before the engine disconnected.
Earlier R2 runs passed 16 backend tests and exercised real TXT/PDF extraction in
the browser; subsequent fixes still need the complete backend/browser suites.

Final Docker-dependent verification is deferred at the user's request. Docker Desktop
cannot attach its WSL data disk
(`ERROR_SHARING_VIOLATION`) after a controlled restart. PostgreSQL is unavailable;
the current backend and browser reruns stopped during database startup. No volumes
were removed. Resume with Docker healthy, rebuild the stack, run `pnpm verify` and
`pnpm test:e2e`, then smoke-test asynchronous extraction through the actual Celery
worker. The user approved skipping Docker work for now and continuing the existing
commit/merge/push workflow. This delivers the implementation without claiming the
remaining integration gates passed.

R2 intentionally has one source/extraction per document. OCR/indexing, search,
answers, replacement, reconciliation and retention are later milestones. Source
quotas cover originals, with preview/failed-attempt disk usage documented separately.

## R3 first slice: DOCX and Markdown — 2 October 2026

- Added DOCX/Markdown to the existing private upload, extraction and source-viewer
  flow. A migration expands the source-kind field; shared access checks and quotas
  apply to both formats.
- DOCX preserves body paragraph, heading and table-cell references without invented
  page numbers. Bounded ZIP reads and defusedxml reject unsafe paths, macros,
  encrypted entries and DTD/entities. Unsupported content produces review warnings.
- Markdown retains literal syntax and Unicode line offsets. HTML, links and remote
  embeds remain inactive text. The viewer displays the appropriate reference labels.

Validation: 12 database-free parser/boundary tests and 3 web unit tests passed,
including existing PDF/TXT regression checks, Nepali text, table anchors and inert
Markdown rendering. Lint/format, TypeScript, Django system checks, OpenAPI generation
and the production web build passed. Offline migration-state comparison found no
drift; applying the migration and running PostgreSQL/API/browser/Compose checks
remain deferred under the user's instruction to skip Docker for now.

Next R3 work: OCR with language/confidence metadata, partial-extraction acceptance,
job cancellation/recovery, tokenizer-bounded chunking and real pinned embeddings.
No new searchable-index or full R3 completion claim is made by this format slice.

## R3 second slice: OCR and extraction review — 4 October 2026

- Added English/Nepali/bilingual OCR for low-text PDF pages, with normalized line
  boxes, identity Unicode spans, engine version and confidence metadata. Every OCR
  result requires review; confidence is not presented as measured accuracy.
- Per-page extraction failures preserve successful pages. Explicit page exclusions
  and a required review note allow owners/curators to accept partial PDF extraction.
  Acceptance records reviewer/time, checks current permissions and revision, and
  retains original pages for inspection. Accepted extraction is not yet indexed.
- Parser-only Tesseract packages, bounded TSV output, page deadlines, one OCR thread,
  process-group cleanup and worker validation retain the offline parser boundary.

Validation: 25 database-free parser/review tests, 5 web unit tests and the setup test
passed. Lint/format, TypeScript, Django system checks, contract generation, offline
migration-state comparison and the production web build passed. A real
Tesseract 5.5.0 smoke run in WSL Ubuntu using `eng+nep` recognized the complete
synthetic English test sentence; its TSV was decoded by the application. This is
not a Nepali accuracy evaluation or a test of the Debian parser container.
PostgreSQL/API review tests are added but execution, migration application, browser
integration and rebuilding/testing the OCR container remain deferred at the user's
request to skip Docker. No full R3 completion claim is made.

Next: ingestion cancellation/recovery, tokenizer-bounded chunking and pinned real
embeddings, then index activation and retrieval. Indexing must honor accepted page
exclusions and keep unreviewed extraction out of searchable results.

## R3 third slice: cancellation and recovery — 5 October 2026

- Added revision-checked cancellation for queued/extracting jobs with current
  contribution permissions. Originals remain downloadable and cancellation can be
  retried. The UI uses server-provided retry eligibility.
- Workers heartbeat every 15 seconds against a 90-second database lease. Beat checks
  expired queued/extracting jobs every 30 seconds, rechecks uploader permissions and
  requeues with fresh attempt IDs, stopping after three recoveries. Manual retry
  resets that budget. Cancelled or terminal jobs are not automatically requeued.
- Cancellation/lease loss stops the worker's spool wait, and the parser supervisor
  terminates the job's owned process group when that spool disappears. Publication
  checks attempt, state and lease while holding the existing workspace/job locks.

Validation: 29 database-free backend tests and 7 web unit tests passed. A real Linux
process-group cancellation smoke test in WSL stopped the synthetic child in 0.50s.
Lint/format, TypeScript, Django system checks, contract generation, offline migration
comparison, the setup test and production web build also passed.
PostgreSQL cancellation/recovery tests are added; database execution, migration
application, live Celery/beat recovery, Compose and browser integration remain
deferred under the instruction to skip Docker. Artifact cleanup after worker crashes
remains future lifecycle work. Next R3 work is chunking and pinned real embeddings.

## R3 fourth slice: chunks, real embeddings and index activation — 5 October 2026

- Added source-preserving chunks with exact Unicode block spans, target 320/hard
  384 tokenizer tokens and up to 40 tokens of same-section overlap. Excluded pages
  never enter the index. PDF pages, Word headings/tables, text paragraph gaps and
  ATX-like Markdown lines define conservative boundaries.
- Pinned multilingual E5-small revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`,
  CPU PyTorch and Transformers. Explicit preparation records file checksums and MIT
  license; runtime is local-only safetensors with remote code disabled. Real query/
  passage prefixes, masked mean pooling, normalized 384-dimensional vectors and
  a counted 512-token input limit are enforced without truncation.
- Added inactive IndexVersion/Chunk/Embedding384 staging, resumable 32-vector
  batches and transactional activation only after completeness/access/lease checks.
  Keyword-only NONE mode is explicit; it never creates synthetic vectors. Retry,
  cancellation and bounded lease recovery are exposed through the source viewer.
  Word warning acceptance records a review note without invented page exclusions.
- Model packages are optional for host use and installed only in the Compose
  ingestion image. Existing environment mode is unchanged. Index preparation is
  an explicit action after extraction/review; search and generation remain future work.

Observed validation: 35 database-free backend tests, 9 web unit tests and the setup
test passed. Real offline E5 inference matched an independent implementation of the
model-card pooling for both query and passage prefixes. All 13 chunks of synthetic
English/Nepali text preserved source coverage and embedded successfully (6.89 seconds
for the check including load on this Windows host; not a retrieval benchmark).
Production web build, TypeScript, Django system checks, OpenAPI generation,
lint/format, offline migration-state comparison and index task registration passed.
The 28 PostgreSQL source/index tests collected successfully; they were not executed.

Migration `0005` and PostgreSQL indexing tests are provided but database execution,
live worker/beat behavior, Compose rebuild and browser integration remain deferred
under the instruction to skip Docker. No full R3 integration-pass claim is made.
First-row table context plus each row must fit 384 tokens; oversized rows fail
explicitly. Markdown Setext recognition and cell-wise packing are not implemented.
An existing index cannot switch profiles until R6 shadow reindexing. Next feature
phase is R4 scoped lexical/vector/hybrid retrieval; complete deferred integration
checks when Docker is available.

## R4 scoped retrieval — 5 October 2026

- Added keyword, semantic and hybrid search with selected collection intersections,
  active-index filtering before both top-k paths, exact-profile enforcement, and a
  scope/access/index recheck after query embedding. No silent profile or scope fallback.
- PostgreSQL weighted title/DOCX-heading/body websearch with NFC matching and
  English/simple Devanagari configuration; exact pgvector cosine; stable top-20
  paths, RRF, overlap deduplication and up to eight passages with document diversity.
- Added Search navigation, collection/method controls, source-block links with
  correct PDF pages, partial-source labels and owner/curator score tables. Changing
  filters cancels pending display updates and clears old results. Errors retain input.
- Stored metadata-only search runs with ranks, hashes, effective scope and timings.
  Query inference is bounded to one per API process and requests to 30/user/minute.
  API image now includes the same local-model dependencies as ingestion.
- Added a reproducible 16-document/10-question development evaluator. Real pinned
  E5 offline cosine retrieval found 6/6 gold evidence groups across five English
  questions and 6/6 across five Nepali questions; MRR 1.0 for each. Observed run:
  12.48 seconds including model load. Report and exact suite hash are saved in
  `docs/evaluations/r4-embedding-development.json`. This small development result
  is not PostgreSQL validation, a held-out evaluation, or general language accuracy.

Validation: 40 database-free backend checks, 13 web unit tests, setup test, lint,
Ruff format, production build/TypeScript, Django checks, offline migration-state
comparison and contract generation
passed. PostgreSQL query compilation was checked without a connection. Four new
PostgreSQL tests cover top-k permission filtering, confusable workspaces, explicit
empty/forged scope, profile mismatch, numerical cosine ordering, heading/Unicode
matching, revocation during embedding and source passage access; they collected
but were not run. Migration application, database evaluation, live API/browser and
Compose checks remain deferred at the user's request to skip Docker. R4 is not yet
fully integration-validated. R5 adds real generation, evidence validation and citations.

## R5 first slice: generation and evidence-validation foundation — 6 October 2026

- Added a bounded local Qwen protocol: up to eight evidence records, 6,000-token
  whole-passage packing, 10,000-token total inputs, six answer blocks and 1,500 words.
  Empty evidence abstains without a model call. One malformed-draft repair is allowed;
  a separate grounding pass must approve every block and the whole answer.
- Exact canonically equivalent quotes resolve to original Unicode source offsets,
  including multi-block references, decomposed/reordered marks and Hangul. Unknown
  evidence IDs, model-supplied metadata, incomplete spans and unsupported/uncertain
  verdicts cannot yield supported answer blocks. Citation metadata comes from the
  server's evidence records; the protocol itself does not grant source access.
- Added stdlib Ollama HTTP access with local origins only, prepared model digest
  checks, non-thinking raw prompts, tokenizer-count checks, bounded response sizes
  and wall deadlines. Usage remains recorded in memory after cancellation or failure;
  ambiguous calls retain estimates and are not automatically retried.
- Added explicit generation preparation/check commands. The pinned real Qwen
  tokenizer downloaded and passed English/Nepali/control-token checks: 48 and 73
  tokens for the respective synthetic test prompts. These are tokenizer results,
  not model-quality measurements. Host artifacts remain ignored by Git.

Validation: 49 database-free backend checks (including nine new protocol/adapter
checks), Django system checks, Ruff lint/format, setup test and diff checks passed.
The HTTP tests use a real loopback test server for redirects, response bounds and
slow-drip deadlines; generated replies are clearly identified contract doubles.
Manual review covered untrusted output, Unicode span boundaries, request limits,
model drift and usage preservation. No frontend, schema or migration changed.

Live preparation reached an unavailable Ollama runtime; no model digest or live
generation result is claimed. Docker/PostgreSQL remain deferred. This completes
only the R5 foundation slice: durable private conversations/turns, atomic quota
reservations, worker leases and cancellation, current-access checks at dispatch/
commit/replay, SSE, exact citation UI and real answer/abstention integration still
remain. No public question endpoint or private-source generation path is exposed.
Continue with those R5 integrations before moving to R6 lifecycle work.

## R5 private conversations and answer delivery — 7 October 2026

- Added private conversation/turn APIs and an unapplied initial migration, with
  idempotent submission, one active turn per conversation, atomic workspace token
  reservations and user/workspace question limits. Generated API contracts include
  the implemented endpoints; question creation is `POST /workspaces/:id/questions`
  with a client-generated conversation UUID rather than a separate empty-chat POST.
- Connected scoped retrieval and exact source-block verification to durable Celery
  answer jobs. Workers fence attempts, renew leases, check current authorization at
  dispatch and publication, persist usage before model calls and retain uncertain
  costs. Recovery retries queued delivery only; interrupted model work requires an
  explicit new turn. Cancellation also interrupts a pending local HTTP response.
- Added authenticated SSE progress/replay, status reads and current-access history
  filtering. Events contain phase metadata; only committed validated answers reach
  the client. Access to all selected retrieval dependencies, including uncited ones,
  is required to read a stored answer. Each question retrieves fresh sources.
- Added the Ask screen, paginated private history, IME-safe submission, stable retry
  intent keys, Stop/Ask again actions and an exact-version citation reader. Unicode
  text highlights are exact; PDF page outlines identify the containing block.
  Restricted sources withhold the whole answer instead of leaving cached excerpts.
- Updated the answers worker image target to include existing local model dependencies.
  No dependencies were added and the host `.env` remains retrieval-only.

Validation: 52 database-free backend tests, 18 web unit tests, the setup test, Ruff
lint/format, ESLint, Django checks and the production Next.js/TypeScript build passed.
OpenAPI regeneration passed without warnings. Offline migration-state comparison and
Celery task discovery passed without contacting PostgreSQL. Seven new PostgreSQL
integration tests were collected, not executed. They cover ownership, idempotency,
actual retrieval SQL with numerical vectors, citations, revocation, cancellation,
recovery and concurrent quota reservations; model outputs are contract doubles.

Docker, migration application, PostgreSQL tests and live API/worker/browser execution
remain deferred at the user's request. No Qwen weights, live answer/abstention result,
latency measurement or model-quality result is claimed. R5 implementation is present,
but its real end-to-end acceptance gate remains open. R6–R8 remain pending.


## 7 October 2026 — R6 lifecycle implementation

- Replaced one-source/one-index constraints with immutable numbered source versions
  and retained indexes. Replacement uploads reuse validated private upload handling,
  require contribution access and a revision, and preserve an idempotent UUID. Newer
  replacements cancel older pending work; only the latest source can activate.
  Current searchable content remains active until its replacement is fully ready.
- Owner workspace reindex builds every active source in the configured E5 or lexical
  profile. The final worker checks the original active-index set and switches the
  entire batch under the workspace lock. Failed/cancelled batches preserve old
  indexes; replacements/deletion cancel in-flight batches. Old READY indexes remain
  available for exact historical citations. Individual uploads/indexing use the
  workspace's established profile, including after an environment-mode change.
- Deletion tombstones the document, clears active indexes, fences pending workers
  and increments the access epoch. Document/source/search/history reads deny deleted
  or purge-requested content. Owner retention cleanup can remove inactive old source
  versions. Physical purge removes original/preview files, extracted blocks, chunks,
  vectors and dependent answer bodies, leaving unavailable markers and minimal IDs.
- Durable storage tombstone journals can be reapplied before opening a restored
  database. Purges retry after partial file removal; parser artifact publication is
  serialized with deletion. Orphan UUID source/spool directories older than one hour
  are cleaned during purge batches. The journal must be preserved independently of
  older database backups; no actual backup/restore exercise has been run.
- Owner limits cover documents, original source bytes, daily question intents and
  daily embedding tokens. Ingestion and semantic query calls charge exact prefixed
  tokenizer counts before dispatch under a workspace lock; uncertain calls keep
  their charge. Existing R5 concurrency and answer-token reservations remain.
- UI includes replacement upload, current searchable versus latest version labels,
  paginated retained sources, explicit deletion confirmation, reindex controls and
  quota forms. Generated API contracts and recovery/purge commands were updated.

Verified locally: 54 database-free backend tests, 20 frontend tests and one setup
test passed (75 total), plus Ruff lint/format, ESLint, Django system checks,
TypeScript and production build. OpenAPI regeneration was warning-free; offline
migration drift, relation SQL compilation and Celery task discovery passed. All
126 backend tests collect, including nine new PostgreSQL lifecycle tests.

R6 is not acceptance-complete: migrations have not been applied, and the PostgreSQL race,
restore and real worker/browser checks remain deferred with Docker. No real model
quality or production-erasure guarantee is claimed.

## 8 October 2026 — R7 reader and recorded evaluation implementation

- Completed the responsive answer/source reader with an accessible width control,
  bounded panel layout and optional browser preference. Below 1100px the source
  replaces the answer view; Back/Escape restores focus to the invoking citation.
  Citation reads now include server-derived version numbers and Older version
  labels. Existing exact Unicode highlights, PDF outlines and access denial remain.
- Replaced the mobile rail toggle with a native modal drawer, including focus
  containment/return and Escape. Added owner evaluation navigation and validated
  list/detail routes. Removed outdated pre-answer capability copy and made empty
  collection actions appropriate to the caller’s role.
- Added a scoped document-status query for Ask, counting accessible/searchable
  documents and newest-source processing. Searchable and processing may overlap
  for replacements; the screen shows an opening/retry snapshot.
- Added owner-only recorded evaluation comparison and case inspection. The existing
  R4 synthetic report is matched to its corpus hash; metrics are recomputed from
  recorded cases, with definitions/denominators and model/backend versions. Failures
  show expected and ranked retrieved canonical document text. Answer, citation,
  human-grounding, abstention, question latency and token measurements stay explicitly
  unmeasured. No new model-quality result or workspace evaluation is claimed.
- Included synthetic artifacts in the backend image context and updated generated
  API contracts. No dependencies, migration or `.env` changes were introduced.
  Optional cloud adapters/provider settings remain unimplemented; R7 uses the local
  profile. Docker image rebuilds have not been run.

Verified locally: 59 database-free backend tests, 24 web tests, one setup test and
four Chromium browser cases (88 total), plus production build, TypeScript, ESLint,
Ruff lint/format, Django checks and warning-free OpenAPI generation. Browser cases
use mocked APIs and cover 360/768/1200/1440px: citation highlights, focus return,
modal navigation, remembered panel size, evaluation list/detail/failure selection,
overflow and axe rules. Screenshots are local test artifacts. All 133 backend tests
collect, including two new unexecuted PostgreSQL membership/status tests.

R7 implementation is present; local API/worker/model end-to-end acceptance remains
open along with prior database/migration/restore gates. Docker/PostgreSQL remain
deferred at the user’s request. R8 frozen evaluation, actual end-to-end evidence,
fresh setup and portfolio handoff remain pending.

## 8 October 2026 — R8 frozen offline evidence and demo handoff

- Froze 24 original fictional documents / 25 source files across three collections
  in workspace A and three confusable-title documents in workspace B. Sources cover
  TXT/MD, native/scanned PDF, DOCX headings/tables, English/Nepali, conflicting memos,
  restricted collections, two leave versions and inert hostile source instructions.
  The scanned PDF's text is an explicitly manual reference, not an OCR result.
- Added 80 versioned labelled cases: 40 development / 40 held-out, each with the
  prescribed category counts and separate topic/fact templates. Labels identify exact
  document/version/block/Unicode offsets/quotes, required facts, caller/scope and
  abstention expectations. A corpus lock and file checksums detect unintended changes.
- Committed the freeze in `a76b057` before inference. Ran the already-prepared pinned
  E5 model on CPU using production chunking/ranking and canonical fixture scope
  simulation. Each split retrieved 41/41 gold spans and full evidence for 33/33
  answerable questions. Held-out English MRR was 0.983; Nepali MRR was 1.0 across
  only three questions. Whole-command time was 33.12 seconds, not request latency.
  There was no post-result label/parameter tuning. All results and exact retrieved
  passages are preserved in `docs/evaluations/r8-offline-semantic.json`.
- Added read-only `run_evaluations --suite r8-v1 --profile local-e5`, with validation
  independent of models/DB and explicitly opted-in offline inference. Default split
  is development; no implicit download, application seeding, reset or provider call.
- Owner diagnostics now expose both R4 document-group and R8 frozen exact-span
  evidence with per-report definitions, versioned expected quotes and ranked chunks.
  R8 artifacts must pass frozen hashes, scope/provenance checks and recomputed scores.
  No-gold cases have `fullEvidence: null`, show abstention unmeasured and stay outside
  the incomplete-evidence filter and answerable-rate denominators. Contracts updated.
- Added `docs/evaluations/R8.md` and `docs/DEMO.md`, with measured provenance, pending
  gates, operating/demo instructions and four preserved desktop/mobile screenshots.
  Screenshots visibly identify mocked answers/comparisons. Backend image context
  includes frozen source artifacts; an actual Docker rebuild remains unverified.

Verified on the existing Windows host: **103 tests passed** (73 DB-free backend,
25 web, one setup and four Chromium/axe cases), plus Ruff lint/format, ESLint,
TypeScript, Django checks, production build and warning-free OpenAPI generation.
All **147 backend tests collect**; collection is not execution of PostgreSQL tests.
All 24 native source files reproduce canonical text/locators with the host parser.
No dependencies, migrations, environment changes or CI bypass were added.

R8 is not acceptance-complete. PostgreSQL keyword/vector/hybrid and real grants,
parser/worker/OCR integration, live Qwen answers/citations/abstention/conflicts,
human answer annotations, prior lifecycle/restore gates and fresh full-stack setup
remain pending under Docker deferral. A database-backed frozen evaluation runner,
guarded demo seed/reset and live recording still need implementation/verification.

## 8 October 2026 — R8 guarded demo tooling

Implemented on `codex/r8-demo-tools` after the offline evidence merge:

- Added host `seed_demo` and `reset_demo`, exposed by `pnpm demo:seed` and
  `pnpm demo:reset --confirm lattice_demo` using ignored `.env.demo`.
- Added a private singleton installation marker with matching storage marker,
  actual local database identity and fixed demo paths. First seed requires empty
  application data/storage. Passwords are operator-supplied, validated and hashed;
  fictional accounts use `.invalid` addresses and seeding dispatches no external work.
- Imports 24 frozen fictional documents / 25 original source versions, four accounts,
  two workspaces and the intended restricted grants. No canonical fixture extraction,
  OCR reference, index or generated answer is imported as live evidence. Jobs are
  cancelled and can be retried through the existing UI after workers are available.
- Reset refuses mismatched markers, unrelated accounts/workspaces, active jobs,
  pending parser requests and storage links/junctions. It retains the database and
  installation marker, removes only disposable demo data/storage, and supports
  interrupted operations. Fresh seed IDs fence messages from a previous demo run.
- Added a Compose demo overlay with distinct project instructions and replacement
  source-storage/parser mounts. Updated demo, operations, security and test guides.
  Original blueprint, frozen labels/report, dependencies, `.env` and API contracts
  are unchanged.

Observed verification:

- **89 DB-free backend tests + 1 Node setup test passed**. This includes 14 new
  demo guard/filesystem cases. **171 backend tests collect**; ten new PostgreSQL
  demo cases are unexecuted, along with the existing deferred database tests.
- Ruff check and format, Django system check and Git whitespace checks passed.
  Migration generation/drift check reports no model drift; database history check
  timed out because the engine remains deferred. No migration was applied.
- Docker Compose CLI configuration merge was validated without an engine, using
  public `.env.example` and no env-file resolution. It selects `lattice_demo` and
  replaces normal source/parser mounts with demo binds in all five backend services.
  This is configuration evidence, not a running-container test.
- Python reviewer findings about interrupted initial marker recovery and retained
  normal parser mounts were fixed and re-reviewed with no remaining findings.

Full R8 acceptance remains open. Real seeding/reset/cascades/recovery, live demo
mounts, ingestion and PostgreSQL grants have not been exercised. API/workers/beat/
parser must be stopped during reset, and all content inside marked demo workspaces
and storage is disposable. Database-backed frozen keyword/vector/hybrid evaluation,
human answer quality/citation/abstention/conflict evidence, lifecycle/restore gates,
fresh setup and live recording still remain. Docker stays deferred at the user's
request; the new tooling does not establish production erasure or full-stack success.
Offline exact-span coverage does not establish generated citation validity, answer
quality or production isolation. The authored short corpus is not a blind benchmark.
