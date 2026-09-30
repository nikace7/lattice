# Application modules

`identity` owns the UUID user model. Django supplies session storage and password hashing.
Authentication endpoints and tenant authorization are not implemented yet.

Add modules when implementing their milestone: `workspaces`, `collections`,
`documents`, `ingestion`, `retrieval`, `conversations`, `providers`, `evaluations`,
and `audit`. Collection scope must constrain database queries before ranking or limits.
