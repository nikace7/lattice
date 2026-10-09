# R8 acceptance workflow

The local implementation is present. Docker, database execution, worker/OCR integration,
live Qwen answers, human labelling, restore, performance and fresh setup remain unverified.
This document describes the commands to run when that deferral is lifted. Do not replace
the frozen corpus or existing offline report to make a run pass.

## PostgreSQL comparison

Use the dedicated local `lattice_demo` database and ignored `.env.demo` from
[the demo guide](../DEMO.md). Apply migrations and explicitly prepare local E5 first.
From the repository root:

```sh
uv run --project backend --extra local --env-file .env.demo python backend/manage.py run_evaluations --suite r8-v1 --profile local-e5 --database --split development
uv run --project backend --extra local --env-file .env.demo python backend/manage.py run_evaluations --suite r8-v1 --profile local-e5 --database --split held-out
```

The command requires DEMO_MODE and verifies the actual local database name. It creates
temporary fictional workspaces, actual memberships/grants, canonical source blocks and
E5 chunk vectors in a transaction. It uses production `corpus`, `candidates` and ranking
for KEYWORD/SEMANTIC/HYBRID on the same data. Records roll back on success and failure;
no originals, email, jobs, SearchRuns or providers are written/dispatched. Stable chunk
IDs make ranking ties reproducible. A shared advisory lock excludes concurrent demo
seed/reset/evaluation commands. Run it while the demo is quiet.

Results include exact-span Recall@8, full evidence, MRR, unauthorized-hit checks and
individual retrieval durations. Timing excludes embedding/model preparation and is
for this small fixture, not a 10k-chunk load benchmark. Real grants inside this harness
do not establish revocation/history/race isolation for the complete application.
Canonical scan text is a manual reference; this harness does not measure OCR.

## Capture actual answers

Seed the disposable demo, then ingest/review/index actual originals. Verify scanned
OCR against its reference. Prepare Qwen explicitly and set only the demo environment
to LOCAL. Use each case's specified persona, question and requested collection IDs
from `fixtures/evals/r8-v1.json` through the existing questions API. The UI supports
one collection or all accessible collections; cases with several explicit collections
require the API's collectionIds list. Authenticate normally and include CSRF protection.

Record the accepted turn UUID against its frozen case ID in an operator JSON object.
Use the production-normalized authorized scope: denied collection requests become an
empty scope. Do not change grants or substitute an owner for a member to bypass a case.
All 40 selected split cases must remain represented; failed/unrun cases stay visible.

```sh
uv run --project backend --env-file .env.demo python backend/manage.py review_answers --split development --turn-map .data/development-turns.json > .data/development-capture.json
uv run --project backend python backend/manage.py review_answers --capture .data/development-capture.json > .data/development-review.json
```

Use UTF-8 output/files (PowerShell 7 or a UTF-8 shell). Capturing requires matching
READY demo markers. It binds each turn to the frozen question, actual persona/workspace
and authorized source scope, requires a recorded model digest, and reads via current
conversation/citation access checks. Citations must reference the frozen permitted
current source versions. Missing turns and inaccessible answers produce no invented
answer. The capture includes actual answer text, source quotes, usage and automatic
citation lookup results. It makes no model call or application data change.

## Human annotation

Keep the capture unchanged; edit only its separate review file. Name the human reviewer.
Template verdicts are null. Split each answer block into atomic factual claims, with
block index, start/end Unicode code-point offsets and the exact text. All non-whitespace
answer characters must be covered without overlap. Keep unsupported or uncertain claims
in the review; do not select only the supported portions. Add a note identifying the
supporting source or the reason for rejection. The initial whole-block spans are an
annotation scaffold; human claim segmentation is still required for a claim-rate result.

- `supported`: true only when the quoted sources support the complete claim; false for
  unsupported/uncertain claims. Leave null until reviewed.
- `factsComplete`: whether every required frozen answer fact is covered for an answerable case.
- `abstentionCorrect`: whether abstention is appropriate for a case without permitted gold evidence.
- `conflictAttributed`: whether a conflict case attributes both positions without inventing a winner.

```sh
uv run --project backend python backend/manage.py review_answers --capture .data/development-capture.json --review .data/development-review.json > .data/development-answer-metrics.json
```

Offline scoring validates frozen labels and capture hash, exact claim text/offsets,
unique cases, nonoverlapping coverage and boolean verdicts. Partly reviewed cases do
not enter human metric denominators. Missing/unreviewed counts remain explicit; empty
denominators are null. `reviewComplete` means all selected cases were reviewed, not
that any quality target passed. A checksum binds files against accidental changes;
it is not a signature proving a live run or independent review. Preserve originals,
reviewer identity, run conditions and development/held-out separation.

## Close the acceptance gates

Run real backend and browser integration tests, including current access, revocation,
tenant/source/history isolation, job recovery, cancellation, purge and independent
tombstone-journal restore. Exercise seed/reset recovery and isolated Compose mounts.
Measure generation latency/tokens and retrieval performance at the planned corpus size.
Repeat setup on a fresh checkout and record the actual walkthrough.

Evaluate the plan's targets against complete held-out evidence: Recall@8 ≥ .85,
exact authorized citation validity 100%, human-supported claims ≥ .90, unsupported
abstention ≥ .90 and zero unauthorized exposure in deterministic tests. Report failures
and missing coverage; never promote offline recall or a mocked UI screenshot into
full-stack acceptance. Optional cloud adapters remain outside the implemented local path.
