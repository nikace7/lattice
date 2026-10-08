# Test locations

- `scripts/project.test.mjs`: setup credential consistency and non-overwrite behavior.
- `backend/tests`: real PostgreSQL/pgvector, health, session rotation, CSRF/origin,
  tenant isolation, role ceilings, revocation, revisions, concurrent owner changes
  scoped pagination, hashed/expired/replayed recovery links, concurrent resets,
  session invalidation, invitation revocation and mail-failure rollback.
  A per-test memory cache isolates throttling from Redis's
  Celery broker; health tests still exercise real Redis.
- `apps/web/src/**/*.test.tsx`: failed login keeps input and sends CSRF with Vitest.
- `apps/web/tests`: production-page Playwright/axe at 360, 768 and 1440 pixels;
  real registration, workspace/collection creation, grant/revoke and logout;
  Mailpit invitation acceptance and password recovery across separate browser sessions.

`pnpm verify` runs host checks and builds; `pnpm test:e2e` runs the browser suite.
Browser tests recreate the reserved `test_lattice_browser` database and use an
isolated Redis cache key prefix. The test database is retained on server shutdown
and reset on the next run. Both ports 4411 and 4412 must be free. Screenshots and
failure traces are gitignored under `apps/web/test-results`.
R2 adds bounded PDF/TXT extraction, Unicode spans, physical-page boxes, encrypted
and corrupt PDFs, upload idempotency/limits, queue retry and access-change tests.
Browser tests also upload Nepali text and a native PDF through the real parser,
check source highlights/focus return, and deny signed-out downloads. Start
`pnpm parser:up` before running them. Citation/indexing and lifecycle gates remain
in `docs/BLUEPRINT.md`.

Without Docker, run `uv run --project backend pytest backend/tests/test_document_formats.py backend/tests/test_ocr_review.py`
and `pnpm --filter @lattice/web test`. These check real DOCX/Markdown parsing,
Unicode/anchor preservation, unsafe ZIP/XML rejection, existing PDF/TXT behavior,
and source-viewer references/inactive embeds. API tests for new formats are in the
PostgreSQL suite and remain separate from these isolated checks.

OCR tests cover Unicode/quoted TSV text, line boxes/confidence, bounded timeouts,
per-page failures, retained successful pages and worker report validation. Web tests
cover mandatory exclusions, review notes/revisions and read-only access. PostgreSQL
review tests additionally cover current permissions, stale/replayed acceptance,
exclusion rules and reviewer provenance; these remain deferred while Docker is skipped.

`backend/tests/test_job_lifecycle.py` runs without a database and checks retry
eligibility, lease renewal rejection, cancellation spool cleanup and owned process
termination. PostgreSQL document tests cover cancellation permissions/revisions,
late publication, recovery attempt fencing, recovery limits and access revocation.
Web unit tests cover cancel/retry controls and preserving access to the original.

`backend/tests/test_chunking_embedding.py` checks chunk source spans, Unicode/page
coverage, section/overlap boundaries, exclusions, table context, vector validation,
explicit model setup and lease fencing without a database. `pnpm models:check`
requires prepared model files and runs real offline E5 inference, comparing query
and passage vectors against reference pooling and embedding bounded English/Nepali
chunks. It is not a retrieval-quality or Nepali-accuracy evaluation.
`backend/tests/test_indexing.py` uses PostgreSQL for staged batch resume, duplicate/
stale delivery, cancellation, access revocation, exclusions and explicit NONE mode.
Those tests do not replace the real-model command; model batches in the DB suite
are controlled test doubles. PostgreSQL/Compose/browser execution remains deferred
while Docker is skipped. UI unit tests exercise index actions and partial-ready labels.

R4: `backend/tests/test_ranking.py` runs without a database and checks deterministic
RRF/diversity, Unicode query boundaries, PostgreSQL query compilation/parameters,
query vector validation and evaluation counts. `backend/tests/test_retrieval.py`
requires PostgreSQL/pgvector for actual lexical/cosine results, scoped top-k, profile
checks, curator boundaries, revocation and passage reads. It uses numerical test
vectors, not an E5 accuracy claim. Search UI tests cover inert excerpts, preserved
input, scope changes/late responses and exact source-block/page navigation.

The host `evaluate_retrieval` management command uses real E5 and a versioned small
development corpus. Default mode compares all paths on temporary PostgreSQL records,
then rolls them back. `--embedding-only` explicitly runs offline cosine ranking and
does not validate the database. See `docs/OPERATIONS.md` for commands and limitations.

R5 foundation: `backend/tests/test_grounding.py` and `test_generation.py` run without
PostgreSQL. They exercise canonical Unicode quote offsets (including reordered
marks, Hangul and astral characters), cross-block spans, unknown/forged citations,
strict output limits, repair limits, uncertain grounding, empty-scope no-call and
access-check failures. Adapter checks cover local-only URLs, redirects, oversized
and slow-drip HTTP responses, digest/token drift, output limits and uncertain usage.
Model replies in these tests are explicit contract doubles, not generated answers
or a quality/permission integration result. `pnpm generation:check --tokenizer-only`
uses the real pinned tokenizer; `pnpm generation:check` needs real Ollama/Qwen and
tests two synthetic cases. Neither completes the durable answer/SSE integration gate.

R5 conversations: `test_turn_protocol.py` checks bounded event cursors, uncertain
usage and source-block mapping without a database. The HTTP adapter suite also
checks cancellation during a real loopback slow-drip response. Seven PostgreSQL
tests in `test_conversations.py` cover private/idempotent turns, scoped retrieval,
exact citations, access revocation (including uncited dependencies), cancellation,
attempt recovery, empty scope and concurrent quota reservations. They use explicit
model contract doubles and numerical retrieval vectors; collected tests are not a
live Qwen or database execution result. PostgreSQL execution remains deferred.

Five Ask UI tests cover IME composition, retry idempotency and preserved input,
disabled generation with readable history, SSE refresh without new generation,
whole-answer removal on citation denial, and Unicode highlights with inert markup.
They run in jsdom, not against the live API, worker or model.


R6: `test_purge_storage.py` runs without a database and checks journal replay,
conflict rejection, bounded file removal and path escape refusal. Document UI tests
also check explicit deletion confirmation/revision and replacement UUID retention
after a network failure. Nine PostgreSQL tests in `test_document_lifecycle.py`
cover replacement replay/supersession, old-version retention, all-at-once shadow
activation, cancelled/failed batches, deletion denial, dependent answer scrubbing,
tombstone restore replay, concurrent embedding reservations and interrupted purge.
These tests are collected but not executed while Docker/PostgreSQL is deferred.
Model/tokenizer doubles in integration tests establish contracts, not model quality.

R7: `test_evaluation_reports.py` verifies recorded corpus hash matching, expected
evidence, report ID allowlisting, owner gating and status-query SQL compilation
without a database. `test_reader_access.py` adds real membership and scoped status
tests; these are collected but not run with PostgreSQL deferred. Citation integration
assertions include source version metadata. Web tests cover incomplete-evidence
inspection, owner-only diagnostics, retry, role-specific empty actions and source
focus return. `reader.spec.ts` runs Chromium with mocked API responses and axe at
360/768/1200/1440px, including modal navigation and remembered source widths.

After `pnpm build`, run the frontend-only browser suite without Docker:

```sh
pnpm --filter @lattice/web exec playwright test --config playwright.reader.config.ts
```

This config starts only Next.js on port 4413; API/model/backend behavior is mocked.
The normal `pnpm test:e2e` still requires the real PostgreSQL test server.

R8: `test_frozen_evaluation.py` validates the frozen 24-document / 80-case suite,
source checksums, gold quotes/versions/scopes and split boundaries. It reproduces
all 24 native file text/locators and checks that the scanned PDF has a raster and
no native text; it does not invoke Tesseract. Span scoring rejects partial/wrong
versions and excludes no-gold questions from answerable metrics. Checked-in E5
results must recompute exactly; changed metrics/out-of-scope hits are rejected.
The validation command uses no database/model. API tests check R8 gold excerpts
and denominators; UI tests distinguish unmeasured abstention from retrieval misses.
Generated contracts make `fullEvidence` nullable and include per-report definitions.
The PostgreSQL owner test now also covers the R8 artifact; it remains unexecuted.

R8 demo tooling: `test_demo_tools.py` has 14 DB-free checks for disabled mode,
explicit target, password validation, database configuration, dedicated paths,
matching markers, pending spool and link-safe cleanup preserving other storage.
Ten PostgreSQL cases cover seed/reset/reseed, real collection grants, nonempty
database, unmarked/mismatched targets, unrelated accounts/workspaces, active jobs
and interrupted marker/seed/storage cleanup recovery. They replace only the
environment guard's database-name query and use real ORM/SQL for data behavior.
These ten cases are collected, not executed during Docker deferral.

```sh
uv run --project backend pytest backend -m "not django_db" -q
```

Compose demo configuration can be merged/checked without starting its engine.
Configuration checks do not prove live mount isolation or ingestion behavior.
