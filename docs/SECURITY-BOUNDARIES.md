# Security boundaries

## Current verification — 15 October 2026

Security hardening adds explicit email verification, token cleanup, production
HTTPS settings, a nonce-based browser CSP, dependency audits and history secret
scanning. The 10 October full-stack baseline is recorded in [EVAL-RESULTS.md](EVAL-RESULTS.md).
On 15 October an isolated native PostgreSQL 15.8/pgvector 0.8.2 instance passed
210 backend tests, including verification concurrency, access revocation and
lifecycle checks. All migrations through identity 0004 applied successfully.
One readiness test failed because Redis
was unavailable. An explicit 0003-to-0004 upgrade preserved an existing account
and reset token, left the account unverified, and enforced verification-token scope.
See the [native database record](evaluations/acceptance/native-database-2026-10-15.json).
This supplements, rather than replaces, PostgreSQL 17/container acceptance. Docker
remains deferred; production TLS/SMTP and external penetration tests have not been
run. Security controls reduce risk; they are not a security certification.

### Dependencies and secrets

Run `pnpm security:audit` for all JavaScript dependencies, including development
tools. Next.js and its lint config are patched to 16.3.8; Vitest is 4.1.11.
Production dependency audit reports no known vulnerabilities. The Python scan of
85 exported lockfile dependencies, including local models, reports none either.

`braces` 3.0.3 has no published upstream fix for
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
The committed pnpm patch bounds combined brace/parenthesis parser nesting before
recursive walkers run. A regression test exercises the installed lint dependency's
parse/compile/expand/stringify string APIs and ordinary globs. Direct caller-created
ASTs bypass this parser mitigation; Lattice's lint dependency uses string patterns.
The audit gate prints the advisory and accepts only that exact advisory, version
and development dependency path, only after its regression test passes, and only
until **12 November 2026 UTC**. All other findings, changed paths, incomplete reports
and expired exceptions fail. Replace the patch with an upstream release when available;
plain `pnpm audit` deliberately continues to show the upstream advisory.

The Security workflow runs on pushes, PRs and weekly: JavaScript/Python audits,
mitigation tests and a checksum-pinned Gitleaks scan of full fetched Git history.
Dependabot covers npm, uv and GitHub Actions. Gitleaks found only five historical
public tokenizer-revision hashes; `.gitleaksignore` contains their exact fingerprints,
not a folder/rule-wide exclusion. Reports redact secrets. No credentials were rotated
or history rewritten because those findings are not credentials.

### Deployment configuration

Local `.env` and Compose remain local development configuration. For a real host:

- Set `DJANGO_DEBUG=false`, `APP_ORIGIN=https://your-host`, explicit
  `DJANGO_ALLOWED_HOSTS`, and a fresh secret. Non-debug Django redirects HTTP to
  HTTPS and enables secure cookies and one-hour HSTS. Health probes alone are
  exempt from the redirect. Increase `DJANGO_HSTS_SECONDS` only after verifying TLS.
- Terminate TLS at a trusted ingress, redirect HTTP there, and send HSTS on web
  responses too. Only enable `DJANGO_TRUST_PROXY=true` when that ingress overwrites
  `X-Forwarded-Proto` and the API cannot be reached directly. The application does
  not trust forwarded client IPs; configure ingress abuse limits for public traffic.
- Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, a verified
  `SMTP_FROM_EMAIL`, and either `SMTP_USE_TLS=true` or `SMTP_USE_SSL=true`.
  Never use the local `.invalid` sender or Mailpit for real delivery.
- Apply migrations, run one beat scheduler, restrict database/runtime credentials,
  retain private storage/backups, and verify recovery and erasure on the deployed host.

HSTS subdomain coverage/preload remain deliberately disabled: they require ownership
and working HTTPS for every affected subdomain. Django's W005/W021 warnings remain
until that deployment decision is made; no warnings are suppressed in code.

The web CSP uses a fresh 256-bit nonce, dynamic rendering and private/no-store HTML.
Production scripts have neither `unsafe-inline` nor `unsafe-eval`. Stylesheets use
self/nonce; inline **style attributes only** remain allowed for bounded source
highlight coordinates and the resizable reader. Documents stay escaped text.
Development alone permits debugger eval and development stylesheet injection.
The browser regression checks hydration, fresh nonces and blocking injected HTML scripts.

DRF endpoints require database-session authentication by default. Only session
bootstrap, login, registration and password recovery/reset allow anonymous access; unsafe requests always
enforce CSRF, including anonymous credentials. Login rotates sessions, password
rules use Django validators, and private API responses use `Cache-Control: no-store`.
UUID IDs are identifiers, not authorization. Health responses contain component
booleans rather than URLs, exception messages, or credentials.

All document/source and future search, history and export paths must use the same
workspace/collection scope resolver before ranking or limiting. This resolver
is implemented in `backend/modules/workspaces/access.py`. Document lists, source
blocks, original downloads and previews recheck this scope; tests cover foreign
workspaces, revoked grants, write-role ceilings and access changes during extraction.
Revocation must withhold affected answer text as well as citation links.

Owners manage membership and grants. Curators write permitted collections;
members/viewers cannot gain write permission from a grant. All roles need active
membership, and foreign-workspace grants are rejected. Workspace row locks,
revision checks and audit records make access mutations atomic and prevent loss
of the last active owner. Collection reads re-check scope on every request.

Authentication uses a conservative 20 requests/minute throttle. Forwarded IP
headers are ignored, so users behind the local proxy share an anonymous throttle
bucket. A deployed proxy needs an explicit trusted-client-IP policy and a
deployment-appropriate rate policy. Recovery has a 5/hour bucket and a worker-side
one-minute account cooldown; owner invitation endpoints have a 30/hour bucket.

Recovery sends mail in Celery to avoid request-time account enumeration through
SMTP timing. Broker failures return a generic 503 for every address. Email payloads
remain private broker data; task argument representations are redacted. Recovery
links expire in 30 minutes and invitations in two days. Random 256-bit secrets are
stored as SHA-256 digests and consumed under user/workspace row locks. All prior
reset links and sessions become invalid after a successful password reset.
Invitation reissue/revoke invalidates the old link; acceptance verifies the email,
active inviter ownership and absence of any existing membership. An invitation
cannot silently reactivate or promote an existing membership.

Links use the configured origin and URL fragments so secrets are absent from HTTP
access logs. The browser removes the fragment, retains it in component memory and
uses a CSRF-protected POST to consume it; opening a link does not mutate access.
Never log request bodies on these endpoints. New registrations require unique
email. Signed-in users can request a one-hour verification link and explicitly
confirm it; links bind the current account and email, use hashed one-use secrets,
and have a locked one-minute resend cooldown. Existing accounts are not silently
marked verified or locked out. Verification is an account status, not an access grant.
There is no email-change endpoint; any future change must clear verification status.
Daily cleanup removes tokens expired or consumed more than 30 days ago.
Invitation SMTP happens inside the workspace transaction, with network timeouts;
an outbox is the upgrade path if mail latency limits access-management throughput.
The recovery worker and session invalidation follow Django's guidance on
[password-reset timing and session hashes](https://docs.djangoproject.com/en/5.2/topics/auth/default/).

Source storage is private and is never mounted into the web or proxy container.
There is no public media route. `.env`, caches, and runtime files are gitignored and
excluded from Docker build contexts. Cloud credentials must never use `NEXT_PUBLIC_`.
Retrieved document instructions are data and never authorize actions or network requests.

Uploads validate extension, signature, UTF-8 and bounded size before saving with
server-generated paths. Workspace locks serialize quota checks and idempotent
creation. The parser container has no network, credentials or original-storage
mount, a read-only root and bounded subprocess CPU/memory/time/output. Its private
spool is shared between jobs, so this is container isolation, not per-file VM
isolation. Treat parser compromise as a risk to concurrent spool jobs.
PDF originals download as attachments; the reader shows generated PNGs, never
embedded active PDF content. Text is escaped by React. Identity normalization
preserves Unicode code points and records source spans, physical pages and boxes.
Scanned/low-text pages require review. Extraction does not imply search readiness.
OCR is local to the offline parser, with allowlisted language arguments and bounded
subprocess/TSV output. Failed pages cannot supply source blocks; malformed reports
cannot bypass review. PDF acceptance rechecks contribution access under the workspace
lock, requires failed/empty-page exclusions and some retained text, and records the
reviewer, time and reason. Index preparation also enforces page exclusions.

Cancellation and manual retries require current contribution access and revision
checks under the workspace lock. Workers cannot renew expired leases or publish
after cancellation, expiry or attempt replacement. Recovery rechecks uploader access
and limits automatic requeues to three. Parser termination targets only the process
group started for that spool job; original files are retained on cancellation.

DOCX uses bounded ZIP reads and defusedxml with DTD/entity rejection. Archive paths
are never extracted and relationship targets are never fetched; macros and encrypted
entries are rejected. Unsupported Word content creates review warnings. Markdown
is rendered as React text, without HTML parsing, clickable source URLs or remote embeds.

Index requests/cancellation require current contribution access and revision checks.
Workers recheck requesting-user access under the workspace lock before staged writes
and activation. All required chunks/vectors must exist before an index is active;
unreviewed warnings, stale attempts, expired leases and cancelled jobs cannot activate.
Chunk spans point to the same extraction; there is no independent browser-supplied
workspace/profile or cross-document chunk linkage. Search applies current collection
access and active-index filtering before either ranking path and its top-k limit.
Model acquisition is explicit and pinned. Runtime checks checksums, loads safetensors
locally with remote code disabled and does not send source text to a provider.
Unexpected indexing errors expose a generic message; logs contain IDs/error types.

Search scopes intersect requested collections with current membership/grants, never
broaden an empty selection, and require identical local profiles for semantic/hybrid.
Query embedding runs outside workspace locks; the complete scope/index/access snapshot
is rechecked under the workspace lock before ranking and response construction.
Concurrent changes produce a conflict instead of releasing stale results. Direct
passage inspection checks the original's current access and matching active index.
Diagnostics require OWNER/CURATOR and use the same readable corpus. Search metadata
contains no raw questions or source text. Client filters cancel pending responses and
clear old excerpts; rendered document text remains inert. PostgreSQL race/access
tests passed in the 10 October baseline and the 15 October native database run.

R5 conversations are private to their creator, including against other workspace
owners. The question API requires current membership and a non-viewer role in LOCAL
mode. The worker supplies authorized retrieval records, verifies source-block mappings,
rechecks the frozen access/index snapshot before and during provider calls, and orders
final storage against revocation under the workspace lock. History and citation reads
recheck current access to every selected retrieval dependency, including uncited
passages; losing any dependency withholds the whole answer. Retained READY indexes
may support old citations after a newer version becomes active.
SSE revalidates the database session and membership on every poll and contains only
phase metadata. Validated text is fetched separately through an authorized read.
The protocol requires a caller check callback, never calls tools, escapes literal
model role tokens in JSON data, and validates strict bounded output. Quotes must
match canonically equivalent text and map to complete original Unicode offsets;
titles, versions and locators come only from server-owned evidence. A second model
pass must approve every block and overall coherence, otherwise the entire answer
is withheld. Model verification remains fallible; contract doubles do not establish
resistance to semantic prompt injection or factual accuracy. No raw model drafts or
hidden reasoning are returned by the protocol.

The local generation adapter checks the prepared model digest before and after
each call, rejects token-count drift, and never downloads models during inference.
Requests only reach the configured local runtime; no browser-supplied origin exists.
In LOCAL mode the private question worker sends authorized passages to that runtime.
General logs contain neither prompts nor raw runtime exceptions. Durable reservations,
usage, attempt fencing and cancellation prevent duplicate publication; ambiguous model
calls retain estimated usage and are not automatically retried. Closing a connection
does not guarantee that the runtime stopped computation. Retention/purge controls
and restore replay passed the 10 October baseline. Current full-stack verification
remains deferred; see the dated evidence rather than inferring a fresh runtime pass.

Compose is a local development configuration. PostgreSQL, Redis, mail and proxy
ports bind only to loopback. The backend and web run as non-root users in containers.
Deployment still requires the environment and ingress configuration above,
database least privilege, abuse limits, backups and retention. A configured CSP
or successful unit test does not establish production readiness.


R6 replacements are immutable, revision-checked and attributed to their uploader;
replays cannot recreate a journaled purged source ID. Workspace-serialized worker
publication checks the latest desired source, current contributor rights, attempt
and lease. Shadow profile activation additionally requires current owner rights
and an unchanged active-index set. Old nondeleted sources remain permission-checked.

Deletion journals are flushed before the database tombstone commits. If database
commit fails afterward, restore replay deliberately fails closed. Purge file paths
must resolve directly beneath the dedicated source root; symlink roots for a source
are rejected. Parser artifact writes hold the same workspace lock and validate the
attempt, preventing a cancelled parser result from recreating purged artifacts.
Stale spool/orphan UUID directories are removed after one hour. Source tombstones
and current permission checks hide dependent answers before the asynchronous scrub;
answer bodies and citation quotes are removed together. User-authored questions,
conversation titles, usage totals and minimal audit IDs remain. Independent copies
of deleted text in user questions or other documents are not automatically detected.
Current journals must accompany restores; backup retention and real restore testing
remain operator responsibilities. PostgreSQL lifecycle checks passed in the
15 October native run; the earlier 10 October restore/browser/worker evidence
does not establish a fresh full-stack pass.
## R7 diagnostics boundary

Recorded evaluations require active owner membership and use a fixed artifact ID,
not a caller-provided filesystem path. Only checked-in synthetic corpus/report data
is exposed; the view neither exports workspace documents nor invokes a provider.
The report must match the versioned corpus hash. Failure inspection renders text
as inert React content. Scoped document status reuses the source API’s readable
document resolver, so inaccessible collections contribute no counts.

Source citation reads retain R5/R6 access checks and add server-derived source
number/older-version metadata. Browser preference storage contains only panel
width. Frontend Chromium/axe checks use mocked APIs and do not establish live
authorization, database isolation or model-grounding correctness. Membership/status
tests passed in the 10 October database baseline; mocks do not replace those tests.

R8 adds a second fixed synthetic report ID. Its suite lock and source checksums,
exact chunk provenance, fixture-scope checks and recomputed metrics must all match
before serving data. Invalid artifacts return the existing safe 503, without paths
or source snippets. Neither evaluation command nor diagnostics seeds or resets application
data. Fixture `MEMBER` means viewer access and is not a production grant model.
Offline scope simulation and UI mocks cannot establish real permission isolation;
the 15 October native PostgreSQL run covers current revocation/history checks;
container and live-worker verification still need the configured stack.

## Guarded disposable demo

`seed_demo` / `reset_demo` are separate host operator commands, not API endpoints.
They require `DEMO_MODE`, local PostgreSQL's actual `lattice_demo` identity and
fixed `.data/demo-storage` / `.data/demo-parser` paths with no links/junctions.
An installation row and matching private storage marker bind database and root.
First seed requires empty application data/storage; the frozen corpus is checked
before import. Passwords come from the ignored demo environment, pass normal
validators, are hashed, and are never printed. Emails use `.invalid`; import
does not dispatch email, model, parser or queue calls. Sources remain unprocessed.

Reset requires a typed target, matching markers, no unrelated accounts/workspaces,
no active jobs or parser requests, and no storage links. A PostgreSQL operator
lock serializes demo commands; workspace locks serialize known worker publication.
API/workers/beat/parser must be stopped throughout reset: locks do not prevent
new application writes or arbitrary external filesystem changes. All content
inside marked workspaces/storage is disposable, including their deletion journals
and database sessions. Normal storage, models and Redis are outside this reset.
Crash states prevent reseeding until cleanup succeeds; each reseed uses fresh IDs.
The demo Compose overlay replaces normal storage/parser mounts by container target.
These guards, PostgreSQL cascades, reset recovery and container checks passed in
the 10 October baseline. Use the production tombstone/backup
procedure for real erasure; a demo reset is not evidence of that procedure.
