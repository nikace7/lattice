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
