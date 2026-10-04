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
integration validation deferred by the user. R3 document formats and OCR/review are implemented;
indexing and R4–R8 remain pending. The ingestion worker
delivers recovery email and document extraction; generation remains future work.

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
