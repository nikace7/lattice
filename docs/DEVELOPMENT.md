# Lattice

A cited knowledge workspace built with Next.js, Django, PostgreSQL/pgvector,
and Celery. Accounts, workspaces, collection organization and access management
are implemented, along with private PDF/DOCX/TXT/Markdown uploads and source inspection.
Low-text PDF pages support English/Nepali OCR with explicit extraction review and page exclusions.
Accepted sources can now produce resumable keyword-only or real local E5 indexes.
Scoped keyword, semantic and hybrid search now include source links and curator
ranking details. R5 adds private conversations, durable answer jobs, validated answer
delivery, cancellation and a citation reader. Generation requires explicitly prepared
local Qwen models and `RAG_MODE=LOCAL`; the default remains retrieval-only.
R6 adds retained source versions, staged workspace reindexing, deletion/purge and
owner-controlled quotas. R7 adds responsive reader controls, accessible mobile navigation,
scoped document status and owner diagnostics for recorded synthetic evaluations.
R8 freezes 24 fictional documents and 80 labelled evaluation cases, records real
offline E5 exact-span retrieval, and includes an illustrated demo/handoff guide.
R8 now includes guarded demo tooling, a rollback-only PostgreSQL comparison runner
and actual-answer capture/human-review commands. The refreshed interface adds clearer
typography, document filters, upload disclosure and keyboard navigation.
Docker acceptance now includes real worker/OCR ingestion, 80 live question attempts,
database/browser tests, backup restore and fresh-checkout setup. Private feedback
and permission-checked Markdown conversation downloads are implemented. Human
answer review remains open, and the local model has recorded false abstentions and
conflict-classification failures; see [current results](docs/EVAL-RESULTS.md).

## Completion status

The local application and UI are implemented. Full quality acceptance is still open:

| Remaining work | Current evidence | Completion condition |
| --- | --- | --- |
| Human answer review | 0/80 cases annotated; offline review packets are available | A human reviews the frozen answers and sources; score the separate annotation files using [the review workflow](docs/evaluations/ACCEPTANCE.md#human-annotation) |
| Model quality | False abstentions and inconsistent conflict handling in the recorded run | Improve using development cases, then evaluate a newly frozen held-out suite without replacing the original results |
| Cold-start performance | One cold answer took 91.281 s, above the 60 s target | Measure loading, retrieval, generation and validation on the working stack; verify any improvement with actual runs |
| Current full-stack verification | 10 October integration baseline passed; 15 October native PostgreSQL checks passed 210/211 tests plus migration 0004; Redis readiness failed | Rerun on the configured PostgreSQL 17/Redis stack, including browser/worker integration and live generation |
| Deployment security acceptance | Account verification, nonce CSP, production settings and security scans implemented; native database checks passed; one development-only upstream advisory has a tested temporary mitigation | Verify actual TLS/SMTP and deployment migrations; replace the braces mitigation before its 12 November audit exception expires |

Docker Desktop's WSL data disk failed to attach on 11 October. Docker work is
currently deferred; the earlier passing baseline does not establish current runtime
health. Production hosting, HTTPS, backup retention/expiry and cloud adapters remain
outside the completed local scope.

An isolated native PostgreSQL 15.8/pgvector 0.8.2 instance allowed database checks
without Docker on 15 October. This supplements the PostgreSQL 17 baseline; it does
not validate the complete configured stack. See the [native database record](docs/evaluations/acceptance/native-database-2026-10-15.json).

Read [security boundaries and deployment settings](docs/SECURITY-BOUNDARIES.md)
for verified controls, the narrow dependency exception and remaining deployment checks.

The complete product specification is in [docs/BLUEPRINT.md](docs/BLUEPRINT.md);
observed progress is in [docs/PROGRESS.md](docs/PROGRESS.md).
Read [R8 evidence](docs/evaluations/R8.md) for measured counts and open acceptance
gates, and [the demo guide](docs/DEMO.md) for screenshots and the live walkthrough.
See [interface design](docs/UI.md) and [the acceptance workflow](docs/evaluations/ACCEPTANCE.md)
for the implemented tools and deferred validation.

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
role, and grant access to restricted collections. Invitations and password recovery
use local Mailpit. Create a collection, then open Documents to upload a source.

Use `pnpm run setup` exactly: bare `pnpm setup` invokes pnpm's own global setup
command instead of this repository's script.

## Commands

| Command | Purpose |
| --- | --- |
| `pnpm run setup` | Install locked JS/Python dependencies and create local configuration |
| `pnpm dev` | Build and start the Compose development stack |
| `pnpm infra:up` | Start PostgreSQL, Redis and Mailpit for host development/tests |
| `pnpm parser:up` | Build and start the offline parser for host development/browser tests |
| `pnpm migrate` | Apply backend migrations using host `.env` |
| `pnpm dev:web` | Host Next.js on port 3000 |
| `pnpm dev:api` | Host Django ASGI on port 4412 with reload |
| `pnpm verify` | Lint, formatting, types, Django checks, migration drift, tests, production web build |
| `pnpm build` | Production frontend build |
| `pnpm test:e2e` | Playwright/axe against production web and a disposable API database |
| `pnpm contracts:generate` | Validate OpenAPI and regenerate TypeScript API types |
| `pnpm models:prepare` | Explicitly download the pinned E5 model/tokenizer into host model storage |
| `pnpm models:check` | Verify real offline embeddings, reference pooling and Unicode chunk spans |
| `pnpm generation:prepare` | Download the pinned Qwen tokenizer and pin an already-installed Ollama model |
| `pnpm generation:check` | Run real synthetic answer/abstention checks; requires local Ollama/Qwen |
| `pnpm infra:down` | Stop this Compose project; keep persistent volumes |

Frozen corpus validation without Docker or models:

```sh
uv run --project backend python backend/manage.py run_evaluations --suite r8-v1 --profile local-e5 --validate-only
```

Add `--embedding-only --split development` instead of `--validate-only` and use
`uv run --project backend --extra local` to run prepared E5 offline. See the evidence
guide before running held-out cases. The command does not evaluate PostgreSQL,
generate answers or seed/reset application data.

Verification uses **real PostgreSQL with pgvector**, never an SQLite substitute:

```sh
pnpm infra:up
pnpm parser:up
pnpm migrate
pnpm verify
pnpm --filter @lattice/web exec playwright install chromium
pnpm test:e2e
```

Index preparation is explicit in the source viewer after extraction/review.
The default `RAG_MODE=RETRIEVAL_ONLY` builds a keyword-only index; configure
`RAG_MODE=LOCAL` before preparing a semantic index. Both use the pinned E5 tokenizer.
Host indexing needs `uv sync --project backend --extra local` and `pnpm models:prepare`.
Compose has separate model storage: prepare it with
`docker compose run --rm --no-deps ingestion-worker python backend/manage.py prepare_models`.
Open **Search** to search ready indexes. Keyword works with NONE and local indexes;
semantic/hybrid require the exact local profile throughout the selected scope.
The API image now includes the local extra for query embeddings. Host semantic
search also needs that extra and prepared model files.
See [operations](docs/OPERATIONS.md) for deployment, retries and current limits.

On Linux CI, use `playwright install --with-deps chromium` to install system libraries.
The E2E runner starts its own production web server on port 4411 and API on 4412,
so run `pnpm build` first if you did not run `pnpm verify`. It recreates only the
reserved `test_lattice_browser` database on the configured PostgreSQL server;
never store real data there. It tests registration, workspaces, grant/revoke,
logout, recovery, invitations, PDF/TXT upload, source locations, responsive layouts
and automated accessibility rules. Extraction uses the real offline parser container.
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
backend/modules/ Identity, workspaces, collections, documents, authorization and audit
backend/pipeline/ Bounded source parser and offline parser supervisor
contracts/      Generated OpenAPI
fixtures/       Synthetic sources, frozen gold labels and development fixtures
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
  changes cannot remove the last active owner. R1 includes email invitations and
  password recovery through local Mailpit, with expiring, one-use links.
- `RAG_MODE=RETRIEVAL_ONLY` is the initial configuration: keyword indexes/search are
  available after explicit preparation. LOCAL additionally needs pinned model files.
  Optional cloud provider adapters remain unimplemented.
- Uploads accept PDF, DOCX and UTF-8 TXT/Markdown up to 25 MiB, with at most 100 PDF pages. Originals,
  extracted passages and PNG previews require current collection access. Scanned
  pages require OCR review; indexing, retained versions and replacement are implemented.
- DOCX uses paragraph/table-cell references; unsupported content produces review
  warnings. Markdown is displayed as literal source text with inactive HTML and embeds.
- The optional `local-models` Compose profile starts Ollama only. It does not pull a
  model. Model preparation and reconciliation/purge commands are explicit. Automated
  `seed_demo` and guarded `demo:reset` are implemented for the dedicated marked
  demo only; PostgreSQL seed/reset interruption recovery has been exercised. Follow the demo guide.
- Checked-in sources/results are original synthetic artifacts. Offline recall does
  not establish answer quality, production isolation or full-stack acceptance.

See [operations](docs/OPERATIONS.md) for development limits and
[security boundaries](docs/SECURITY-BOUNDARIES.md) before adding product endpoints.
