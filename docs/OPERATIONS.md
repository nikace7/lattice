# Local operations

Use `pnpm run setup` followed by `pnpm dev`. Docker Desktop must use Linux containers.
The first build pulls pinned runtime images; it does not download embedding or
generation weights. Ports 4400, 5440, 6380, 8026 and 1026 must be free.

`docker compose ps` shows service status. `docker compose logs api` diagnoses API
startup, and `docker compose logs migrate` diagnoses migrations. Health endpoints
are `/health/live` and `/health/ready` through port 4400. Readiness requires the
vector extension migration and a writable private storage volume.

The API waits for migrations and Redis. Workers consume separate `ingestion` and
`answers` queues with bounded concurrency. Beat has persistent scheduler state;
there are no scheduled product tasks yet. Future parsing requires its own bounded,
network-isolated process; a generic Celery worker is not a parser security boundary.

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
