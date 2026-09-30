# Lattice

A cited knowledge workspace built with Next.js, Django, PostgreSQL/pgvector,
and Celery. This repository currently contains the **project foundation**.
Uploads, tenant authorization, search, and answer generation are not implemented yet.
The complete product specification is in [docs/BLUEPRINT.md](docs/BLUEPRINT.md);
observed progress is in [docs/PROGRESS.md](docs/PROGRESS.md).

## First run

Install Node 22.12+ (22 LTS or 24), pnpm 10.33.4, Python 3.12, uv, and Docker
Desktop with Linux containers. `.node-version` pins the CI/container baseline.
Run from the repository root in PowerShell, Bash, or another terminal:

```sh
pnpm run setup
pnpm dev
```

Open **http://localhost:4400**. Setup installs locked dependencies, creates a
gitignored `.env` with random local credentials, and creates private host data
directories. It preserves an existing `.env`. Compose applies migrations before
starting the API and workers. No cloud key or model download is needed.

`pnpm dev` runs the full development stack in the foreground. Source edits in
`apps/web/src`, `backend/config`, and `backend/modules` reload automatically.
Restart with `pnpm dev` after dependency, migration, or infrastructure changes.
Stop with Ctrl+C; `pnpm infra:down` removes containers while retaining data volumes.
Mailpit captures local mail at http://localhost:8026; nothing is sent externally.

Use `pnpm run setup` exactly: bare `pnpm setup` invokes pnpm's own global setup
command instead of this repository's script.

## Commands

| Command | Purpose |
| --- | --- |
| `pnpm run setup` | Install locked JS/Python dependencies and create local configuration |
| `pnpm dev` | Build and start the Compose development stack |
| `pnpm infra:up` | Start PostgreSQL, Redis and Mailpit for host development/tests |
| `pnpm migrate` | Apply backend migrations using host `.env` |
| `pnpm dev:web` | Host Next.js on port 3000 |
| `pnpm dev:api` | Host Django ASGI on port 8000 with reload |
| `pnpm verify` | Lint, formatting, types, Django checks, migration drift, tests, production web build |
| `pnpm build` | Production frontend build |
| `pnpm test:e2e` | Playwright/axe against the production frontend build |
| `pnpm contracts:generate` | Validate OpenAPI and regenerate TypeScript API types |
| `pnpm infra:down` | Stop this Compose project; keep persistent volumes |

Verification uses **real PostgreSQL with pgvector**, never an SQLite substitute:

```sh
pnpm infra:up
pnpm migrate
pnpm verify
pnpm --filter @lattice/web exec playwright install chromium
pnpm test:e2e
```

On Linux CI, use `playwright install --with-deps chromium` to install system libraries.
The E2E runner starts its own production web server on port 4411, so run `pnpm build`
first if you did not run `pnpm verify`. It currently tests the foundation screen only.
Backend commands also work from `backend`, e.g. `uv run python manage.py migrate`.

Host tools use PostgreSQL port **5440**, Redis **6380**, and SMTP **1026**, all bound
to loopback. Compose overrides these with internal service addresses. Host storage
under `.data` is separate from Compose named storage volumes. Use the full Compose
origin for future session/CSRF flows; host ports 3000/8000 are individual development
servers, not a configured cross-origin authentication flow.

## Layout

```text
apps/web/        Next.js App Router, design tokens, Vitest and Playwright
backend/config/ Django settings, ASGI, Celery, health endpoints
backend/modules/ UUID identity model; future domain modules live here
backend/pipeline/ Future bounded ingestion/retrieval services
contracts/      Generated OpenAPI
fixtures/       Corpus and evaluation conventions (no measured corpus yet)
infra/          Container definitions and Caddy routing
scripts/        Cross-platform setup and verification
tests/          Test layout notes
docs/           Blueprint, progress, design and operating notes
```

## Boundaries

- `GET /health/live` checks the API process. `GET /health/ready` checks PostgreSQL's
  vector extension, Redis, and private storage writability. Readiness is infrastructure
  readiness, not proof that product features or a model are available.
- Django uses a UUID user model from the first migration, database sessions, CSRF
  middleware, and authentication-required DRF defaults. There are no login or tenant
  endpoints yet; R1's authorization acceptance gate remains open.
- `RAG_MODE=RETRIEVAL_ONLY` is the initial configuration. This does not claim retrieval
  exists. Other mode names are validated, but provider behavior is not implemented.
- The optional `local-models` Compose profile starts Ollama only. It does not pull a
  model. `models:prepare`, demo seeding/reset, reconciliation/purge commands, and
  evaluations belong to the relevant product milestones and are not fake success stubs.
- No real documents, credentials, generated answers, model accuracy claims, or
  evaluation scores ship with this initialization.

See [operations](docs/OPERATIONS.md) for development limits and
[security boundaries](docs/SECURITY-BOUNDARIES.md) before adding product endpoints.
