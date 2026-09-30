# Test locations

- `scripts/project.test.mjs`: setup credential consistency and non-overwrite behavior.
- `backend/tests`: real PostgreSQL/pgvector migration, UUID/session baseline and health errors.
- `apps/web/src/**/*.test.tsx`: starter content contract with Vitest.
- `apps/web/tests`: production-page Playwright/axe smoke at 360, 768 and 1440 pixels.

`pnpm verify` runs host checks and builds; `pnpm test:e2e` runs the browser suite.
Isolation, ingestion, citation and lifecycle gates remain in `docs/BLUEPRINT.md`.
