# API contracts

`pnpm contracts:generate` validates the Django-generated `openapi.yaml` and writes
`apps/web/src/lib/api.generated.ts`. Commit both. CI regenerates and checks for drift.
Only the implemented health endpoints appear initially; product API shapes remain
in the blueprint until their behavior exists.
