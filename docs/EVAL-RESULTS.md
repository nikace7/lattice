# Acceptance results — 10 October 2026

The application implementation and local runtime checks are complete. Full answer
quality acceptance is **open**: human claim annotations are missing, the local
model falsely abstains on supported questions and conflict classification is
inconsistent. These observations are retained below rather than converted into a
passing accuracy claim.

## Conditions and provenance

Windows host: Intel Core i9-13950HX, 32 logical processors, 31.77 GiB RAM;
Docker Linux engine limited to about 15.5 GiB. Other unrelated project services
remained running. Node 24.20.0, pnpm 10.33.4, uv 0.11.11, Python 3.12.13,
PostgreSQL 17.10/pgvector 0.8.2, Redis 7.4.7, Tesseract 5.3.0 and Ollama 0.11.10.

The normal environment stays retrieval-only. The isolated `lattice-demo` project
uses its own database, storage and parser spool. LOCAL mode, explicitly prepared
models and an increased demo-only answer-token ceiling permitted the 80-case run;
no cloud provider was called. Local operator environments and backup originals
remain ignored, with no credentials committed.

- Frozen suite: `r8-v1`, 24 fictional documents, 25 source versions, 80 cases.
  SHA-256: `f8653ad9deb5cb73429d7f70b6737198f1dd680373ce541a3a05b98958e3ce4e`.
- E5: `intfloat/multilingual-e5-small` revision
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions, CPU/two threads.
- Qwen: `qwen3:4b`, digest
  `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`;
  tokenizer `Qwen/Qwen3-4B` revision
  `1cfa9a7208912126459214e8b04321603b3df60c`;
  profile `qwen3-raw-template-v1`, context 16384, thinking disabled, temperature 0.
- Runtime baseline: `92d0ad0`; final feedback/export implementation: `fb65bd8`.
  Model prompts, frozen labels and retrieval settings were unchanged in the held-out run.

All 24 current originals passed actual HTTP → Redis worker → offline parser → E5
indexing. Native normalized blocks matched their frozen references. The scanned
drill produced three exact reference lines; its actual page preview was inspected
and explicitly accepted. This was an operator review by Codex, not human answer
annotation or a general OCR accuracy measurement.

## SQL retrieval on canonical fixtures

The database runner uses real membership/grant scope and production SQL, with
canonical passages and actual E5 vectors. Temporary records roll back. These
reports are separate from actual ingestion and live-answer results.

| Split | KEYWORD gold spans / required | SEMANTIC | HYBRID | Unauthorized hits |
| --- | ---: | ---: | ---: | ---: |
| Development | 7 / 41 | 41 / 41 | 41 / 41 | 0 |
| Held-out | 5 / 41 | 41 / 41 | 41 / 41 | 0 |

Semantic/hybrid full evidence: 33/33 answerable questions in each split; English
38/38 spans and Nepali 3/3 spans. Held-out English MRR is 0.9833; other split/language
MRRs are 1.0. Lexical retrieval failed many paraphrases and all three Nepali cases
per split. This small authored corpus is an easy diagnostic, not general retrieval
coverage. Query embedding and HTTP are excluded from SQL timing.

Reports: [development](evaluations/acceptance/r8-postgres-development.json),
[held-out](evaluations/acceptance/r8-postgres-held-out.json).

## Actual answers

Cases use their specified persona, question and authorized collection scope.
Failed generations are retained; no replacement answer was silently submitted.
Permission-denied requests resolve to empty evidence. No held-out labels were used
to tune the model. A clarification tested on six development diagnostics did not
improve their status and was discarded before held-out generation.

| Split | ANSWERED | INSUFFICIENT_EVIDENCE | FAILED | Exact authorized citations | Completion p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Development | 20 | 19 | 1 | 25 / 25 | 49.27 s, 39 measured intervals |
| Held-out | 25 | 15 | 0 | 35 / 35 | 44.09 s, 40 intervals |

Completion intervals include POST, queue/retrieval, generation, grounding and
two-second status polling. Development case 34 encountered a worker
OperationalError; its resumed terminal read has no invented elapsed interval.
Totals: development 40,883 known input and 4,316 output tokens plus a 4,073-token
uncertain reservation; held-out 41,866 input and 4,085 output tokens. Counts include
generation/validation calls. [Rollup](evaluations/acceptance/live-rollup.json).

Twelve development and eight held-out cases with permitted gold evidence returned
INSUFFICIENT_EVIDENCE. All three held-out conflict cases returned ANSWERED rather
than CONFLICTING_EVIDENCE. Those are automatic protocol/label observations;
claim support, factual completeness and attributed conflict handling require a
human reading of the complete answers and sources.

Human review: **0/80 cases**. Human-supported claims, required-fact completeness,
unsupported abstention and conflict handling remain `null`. Exact quotation/access
validity does not prove the answer follows from its quote. A new model/prompt
iteration must use development cases and a newly frozen held-out evaluation;
this run must remain unchanged.

Captures: [development](evaluations/acceptance/development-capture.json),
[held-out](evaluations/acceptance/held-out-capture.json). Blank review files:
[development](evaluations/acceptance/development-review.json),
[held-out](evaluations/acceptance/held-out-review.json). Scored automatic results:
[development](evaluations/acceptance/development-answer-metrics.json),
[held-out](evaluations/acceptance/held-out-answer-metrics.json).
Follow [the review workflow](evaluations/ACCEPTANCE.md) to annotate without modifying
captures or assigning fabricated human verdicts.

## Performance

The 10k load replicates authorized frozen Cedar passages and their real vectors;
it is not 10,000 independent documents. Each mode runs 40 iterations through
production scope, SQL candidates and ranking, excluding query embedding, model
preparation and HTTP. p95 is the nearest-rank 38th sorted sample. All temporary
records roll back and unauthorized hits remain zero.

The first run overlapped live generation/builds: KEYWORD p95 1047 ms, SEMANTIC
94 ms, HYBRID 1032 ms. [Original report](evaluations/acceptance/10k-sql-load-concurrent.json).
After live generation, browser journeys and image builds finished, a quiet rerun
measured KEYWORD **422 ms**, SEMANTIC **47 ms**, HYBRID **422 ms** p95; all modes
were below 800 ms with zero unauthorized hits and successful rollback.
[Quiet report](evaluations/acceptance/10k-sql-load-quiet.json). Unrelated background
services remained running, so this is an observed local result, not a dedicated
hardware or full HTTP benchmark.

One fresh API/worker restart probe delivered its first accepted SSE event in
**109 ms**, below the 500 ms target. It reconnected using Last-Event-ID after the
55-second stream lifetime without resubmitting. Completion took **91.281 seconds**,
including roughly 18 seconds until generation started, 51 seconds until validation
and 21 seconds validating. This cold process sample exceeds the 60-second local
target and stays separate from the warm split p95. Prepared files existed; files
being cached does not mean a worker's model is already loaded.
[Event timings](evaluations/acceptance/sse-result.json).

Actual native 20-page PDF upload → READY index took **24.139 s** including real
extraction (**5.887 s**), worker embedding/indexing and UI polling, below the
60-second target. This is one deterministic native fixture, not an OCR throughput
benchmark. [Walkthrough measurements](evaluations/acceptance/walkthrough.json).

## Runtime, lifecycle and UI checks

- `pnpm verify`: lint/format/type/system/build passed; 192 real PostgreSQL backend
  tests, 30 web tests and one setup test passed. Migration drift was empty;
  normal-environment history lookup warned because that database was not on the
  demo server. Separate demo migration consistency/drift and `migrate --check`
  checks passed. A UUID ranking tie in a
  mock-generator test was fixed with distinct fixture vectors, preserving both
  retrieved dependencies and its revocation assertion.
- `pnpm test:e2e`: all 16 passed after starting the normal test parser. Six journeys
  use real Django/PostgreSQL/Mailpit/parser with eager test Celery; ten UI/reader
  journeys use labelled mocked API data. The separate actual demo browser uses
  real Redis workers and confirms feedback, Markdown download, source highlight,
  focus return and 360px overflow. Automated axe checks do not establish complete
  WCAG conformance. [Live browser record](evaluations/acceptance/live-ui.json).
- Actual consistent `pg_dump`/private storage backup restored into another local
  database and empty storage. A newer independent tombstone journal was overlaid
  and production purge replayed twice. Checks preserved 25 original checksums,
  24 active profiles, 25 real citation lookups; two forbidden lookups were denied.
  The deleted probe's files/text/vectors were removed. The clone had no API/workers.
  [Restore result](evaluations/acceptance/restore-result.json). Final migration
  `0003` was subsequently applied to the restored clone too.
- A managed fresh checkout at `92d0ad0` installed locked dependencies, built, used
  new Compose volumes and migrated. Real registration, English/Nepali TXT upload,
  keyword index/search and anonymous-original 401 passed after explicit E5
  preparation. This was the same host, not a new machine; it did not pull a new
  Qwen model. [Fresh setup](evaluations/acceptance/fresh-browser.json).
- A separate fresh-server `lattice_demo` installation exercised real guarded
  seed/reset, idempotent seed, controlled source-write interruption (SEEDING)
  and post-SQL filesystem interruption (RESETTING), followed by safe recovery.
  No environment/marker guard was bypassed. [Recovery](evaluations/acceptance/reset-result.json).
- Final Compose images were rebuilt for `fb65bd8`, migrated and started healthy.
  Normal application data and unrelated project services were preserved. Fresh
  acceptance containers were removed without deleting their volumes; ignored
  environments, logs and storage were saved locally before archiving that checkout.

The [demo guide](DEMO.md) includes actual screenshots and the two-minute recording.
Production HTTPS deployment, backup retention/expiry and optional cloud adapters
are outside this local acceptance. No remote CI result is used as the merge gate.

## 11 October 2026 — diagnostic continuation

The next development-only model diagnostic did not produce an answer: Docker
Desktop exited during its first request. A stale socket directory was preserved
and moved aside; the subsequent restart failed to attach Docker's WSL data disk.
A clean WSL restart did not restore the engine. These attempts do not establish
the cause of the original exit or a model-quality/performance result. The user
then requested Docker-independent work. No prompt, runtime thread setting, model
pin, frozen labels or existing reports were changed.

New generation calls now persist optional load, prompt-processing and generation
durations alongside locally measured request time in their usage records, including
failed requests. This permits the next live run to separate model loading from
inference without logging private prompts or adding a model call. Old records
remain valid and token charging is unchanged. This is diagnostic instrumentation,
not a latency or answer-quality improvement claim.

Observed verification: 110 Docker-independent backend tests passed; 89 PostgreSQL
tests were deselected. Ruff lint/format, Django system checks and whitespace checks
passed. Python and general code reviews found no blockers. Live model and database
integration checks were not repeated for this change. The prior 10 October results
above remain the baseline; human review and model-quality gates stay open.
