# Application modules

`identity` owns the UUID user model. Django supplies session storage and password hashing.
It also provides session, registration, login and logout endpoints with CSRF checks.

`workspaces` owns membership, roles and the shared collection scope resolver;
`collections` owns visibility and grants; `audit` records metadata for mutations.
Access mutations lock the workspace row and validate the current revision before
writing, including protection against concurrent removal of the last owner.

Add modules when implementing their milestone:
`documents`, `ingestion`, `retrieval`, `conversations`, `providers`, `evaluations`,
and other provider integrations. Collection scope must constrain database queries
before ranking or limits.
