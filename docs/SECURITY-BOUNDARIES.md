# Security boundaries

The foundation exposes two read-only health endpoints. Every future DRF endpoint
inherits session authentication and authenticated permissions unless explicitly
overridden. UUID IDs are identifiers, not authorization. Health responses contain
component booleans rather than URLs, exception messages, or credentials.

All future document, search, source, history and export paths must use the same
workspace/collection scope resolver before ranking or limiting. This resolver does
not exist yet. Do not expose document endpoints until isolation tests are in place.
Revocation must withhold affected answer text as well as citation links.

Source storage is private and is never mounted into the web or proxy container.
There is no public media route. `.env`, caches, and runtime files are gitignored and
excluded from Docker build contexts. Cloud credentials must never use `NEXT_PUBLIC_`.
Retrieved document instructions are data and never authorize actions or network requests.

Compose is a local development configuration. PostgreSQL, Redis, mail and proxy
ports bind only to loopback. The backend and web run as non-root users in containers.
Before deploying, configure HTTPS, production settings/hosts, proxy trust, HSTS,
CSP, database least privilege, authentication throttling, upload isolation/limits,
backups and retention. These controls depend on product and deployment work; the
starter is not a production-ready multi-tenant RAG service.
