# Lattice

A cited knowledge workspace built with Next.js, Django, PostgreSQL/pgvector,
and Celery. Accounts, workspaces, collection organization and access management
are implemented. Uploads, search, and answer generation are not implemented yet.
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

Create an account, then a workspace. Its creator becomes the owner. Owners can add
existing accounts by username under **People & access**, choose their workspace
role, and grant access to restricted collections. Email invitations and password
recovery are still pending; this build does not send account mail.

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
| `pnpm dev:api` | Host Django ASGI on port 4412 with reload |
| `pnpm verify` | Lint, formatting, types, Django checks, migration drift, tests, production web build |
| `pnpm build` | Production frontend build |
| `pnpm test:e2e` | Playwright/axe against production web and a disposable API database |
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
The E2E runner starts its own production web server on port 4411 and API on 4412,
so run `pnpm build` first if you did not run `pnpm verify`. It recreates only the
reserved `test_lattice_browser` database on the configured PostgreSQL server;
never store real data there. It tests registration, workspaces, grant/revoke,
logout, responsive layouts and automated accessibility rules.
Backend commands also work from `backend`, e.g. `uv run python manage.py migrate`.

Host tools use PostgreSQL port **5440**, Redis **6380**, and SMTP **1026**, all bound
to loopback. Compose overrides these with internal service addresses. Host storage
under `.data` is separate from Compose named storage volumes. Use the full Compose
origin for the simplest setup. For host development, set `APP_ORIGIN` to
`http://localhost:3000` before starting `pnpm dev:api` and `pnpm dev:web` in separate
terminals. Next forwards `/api` to loopback port 4412, keeping cookies and requests
on the same browser origin. Restore the origin to port 4400 for Compose.
Use `127.0.0.1` in host database/Redis URLs to avoid IPv6 fallback delays on Windows.

## Layout

```text
apps/web/        Next.js App Router, design tokens, Vitest and Playwright
backend/config/ Django settings, ASGI, Celery, health endpoints
backend/modules/ Identity, workspaces, collections, authorization and audit
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
- Django uses UUID identities, database sessions, CSRF checks including anonymous
  login/registration, and authentication-required DRF defaults. Collection queries
  enforce membership and grants before pagination; workspace roles cap permissions.
- Access mutations are atomic, audited and revision-checked. Concurrent owner
  changes cannot remove the last active owner. R1 remains partial until account
  recovery and invitations are implemented.
- `RAG_MODE=RETRIEVAL_ONLY` is the initial configuration. This does not claim retrieval
  exists. Other mode names are validated, but provider behavior is not implemented.
- The optional `local-models` Compose profile starts Ollama only. It does not pull a
  model. `models:prepare`, demo seeding/reset, reconciliation/purge commands, and
  evaluations belong to the relevant product milestones and are not fake success stubs.
- No real documents, credentials, generated answers, model accuracy claims, or
  evaluation scores ship with this initialization.

See [operations](docs/OPERATIONS.md) for development limits and
[security boundaries](docs/SECURITY-BOUNDARIES.md) before adding product endpoints.
