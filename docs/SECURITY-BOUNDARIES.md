# Security boundaries

DRF endpoints require database-session authentication by default. Only session
bootstrap, login, registration and password recovery/reset allow anonymous access; unsafe requests always
enforce CSRF, including anonymous credentials. Login rotates sessions, password
rules use Django validators, and private API responses use `Cache-Control: no-store`.
UUID IDs are identifiers, not authorization. Health responses contain component
booleans rather than URLs, exception messages, or credentials.

All future document, search, source, history and export paths must use the same
workspace/collection scope resolver before ranking or limiting. This resolver
is implemented in `backend/modules/workspaces/access.py`. Document endpoints still
need their own isolation tests before exposure.
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

Compose is a local development configuration. PostgreSQL, Redis, mail and proxy
ports bind only to loopback. The backend and web run as non-root users in containers.
Before deploying, configure HTTPS, production settings/hosts, proxy trust, HSTS,
CSP, database least privilege, authentication rate policy, upload isolation/limits,
backups and retention. These controls depend on product and deployment work; the
starter is not a production-ready multi-tenant RAG service.
