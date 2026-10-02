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
private storage. Answers are not available yet.

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
`answers` queues with bounded concurrency. Beat has persistent scheduler state;
there are no scheduled product tasks yet. The ingestion worker sends extraction
requests through `.data/parser` to the separate offline parser container.

For host development and browser tests, run `pnpm parser:up` as well as
`pnpm infra:up`. The parser has no network, database credentials or source-storage
mount. It runs two bounded subprocesses with a 305-second deadline, 30 seconds per
page, and a 1 GiB container limit. Rebuild it after changes to `backend/pipeline`.
On Linux, grant the host user and container UID 10001 access to the private spool
directory; do not expose it through the web server or make it world-writable.

Uploads allow PDF or UTF-8 TXT, 25 MiB/file, 100 PDF pages, 2 million extracted
characters and 20,000 blocks. Workspaces allow 500 sources and default to 2 GiB of
original files (`MAX_WORKSPACE_STORAGE_BYTES`); previews and failed-attempt artifacts
are additional disk usage. Encrypted PDFs are rejected. Scans/low-text pages need
review; OCR and indexing are not part of R2. Each document has one immutable source.

The source viewer reports queued, extracting, extracted, needs-review or failed.
Retry transient failures after restoring the parser/broker; jobs stuck for ten
minutes can be retried. Attempt IDs prevent old workers publishing after a retry.
Requests normally remove their temporary spool directory on completion. Worker
crashes can leave spool data, and failed attempts can leave private previews;
automated reconciliation, replacement and retention belong to the lifecycle phase.
Treat spool data as confidential and stop workers/parser before manual cleanup.

`pnpm infra:down` retains all data. There is deliberately no destructive reset
command. Do not remove volumes to fix a migration or credential mismatch. If `.env`
is lost after PostgreSQL was initialized, restore the prior credentials or perform
an intentional database credential rotation; setup cannot rotate a persisted DB.

The local data stores are `lattice_postgres`, `lattice_redis`, `lattice_storage`,
`lattice_models`, and `lattice_beat`. Host `.data` is separate. Backups/restore and
deletion-retention policy must be implemented and verified before storing real
documents; no backup retention or purge guarantees are claimed at initialization.

Optional Ollama: `docker compose --profile local-models up -d ollama`. The service
has no published host port and no preinstalled models. A future explicit model
preparation command must pin E5 revision/Qwen digest and record licenses, hardware,
disk use and measured behavior. There is no automatic cloud or fixture fallback.

Dependency updates: use pnpm for JS and `uv add`/`uv lock` for Python, review both
lockfiles, then run `pnpm verify` and `pnpm test:e2e`. The Next.js lint CLI is run
separately because [Next.js 16 builds do not run lint](https://nextjs.org/docs/app/api-reference/config/eslint).
Python container dependencies use [uv's locked sync](https://docs.astral.sh/uv/concepts/projects/sync/).
