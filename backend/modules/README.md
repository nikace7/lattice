# Application modules

`identity` owns the UUID user model. Django supplies session storage and password hashing.
It provides sessions, registration, login/logout, recovery, invitations and explicit
email verification with CSRF checks. Expired/consumed action tokens are pruned by
the daily cleanup task after a 30-day retention window.

`workspaces` owns membership, roles and the shared collection scope resolver;
`collections` owns visibility and grants; `audit/service.py` records mutation metadata.
Access mutations lock the workspace row and validate the current revision before
writing, including protection against concurrent removal of the last owner.

`documents` owns immutable originals, extraction jobs/versions, exact source blocks,
scoped uploads/downloads/previews and retry fencing. `access.py` resolves readable
documents/sources, `upload_api.py` handles upload/replacement, and `api.py` handles
reads and processing actions. Parser code lives in `pipeline`.

`retrieval` owns scoped search, frozen evaluations and answer review. `conversations`
owns private turns, events, feedback and exports. Collection scope constrains queries
before ranking or limits. Provider calls and grounded answer validation live in
`pipeline/generation.py` and `pipeline/grounding.py`.

HTTP serializer/revision helpers live in `config/api.py`; domain access helpers
live in `workspaces/access.py`. Other domains do not import workspace API views.
The web separates authentication/account actions from the workspace library shell;
its shared API client uses generated OpenAPI types.
