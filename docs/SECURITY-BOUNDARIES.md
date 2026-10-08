# Security boundaries

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
email; email verification/change UI and expired-token retention are future work.
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
clear old excerpts; rendered document text remains inert. PostgreSQL race/access tests
are provided but their execution remains deferred, so these are implementation
boundaries rather than a claim of completed integration verification.

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
does not guarantee that the runtime stopped computation. R6 retention/purge controls
are implemented with integration verification deferred. These database boundaries have tests awaiting real PostgreSQL execution;
live runtime and browser integration remain unverified while Docker is deferred.

Compose is a local development configuration. PostgreSQL, Redis, mail and proxy
ports bind only to loopback. The backend and web run as non-root users in containers.
Before deploying, configure HTTPS, production settings/hosts, proxy trust, HSTS,
CSP, database least privilege, authentication rate policy, upload isolation/limits,
backups and retention. These controls depend on product and deployment work; the
starter is not a production-ready multi-tenant RAG service.


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
remain operator responsibilities. These boundaries have not yet passed PostgreSQL
or live browser/worker integration tests.
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
authorization, database isolation or model-grounding correctness. The new real
membership/status tests are collected but remain unexecuted without PostgreSQL.
