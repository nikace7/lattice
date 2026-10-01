# API contracts

`pnpm contracts:generate` validates the Django-generated `openapi.yaml` and writes
`apps/web/src/lib/api.generated.ts`. Commit both. CI regenerates and checks for drift.
The schema includes health, sessions, workspaces, memberships, collections and
grants. Unimplemented document/search/answer APIs remain in the blueprint.
