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

R1 is **in progress**, not complete. Workspace/membership/collection models,
login/recovery/invitations and the shared authorization scope resolver remain next.
R2–R8 have not started. Celery queues and beat currently have no product tasks.

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

GitHub Actions is configured but has not run on a remote repository. The optional
Ollama profile and any model download/inference remain untested and uninstalled.
No RAG quality, performance, tenant isolation, or live generation result is claimed.
