# Retrieval protocol

Every request resolves active membership and readable collections before selecting
current READY indexes. An explicit denied collection produces an empty scope; it
never broadens to every accessible collection. Search snapshots the access epoch,
scope and index/profile IDs, embeds outside the workspace lock, then rechecks them
under that lock before reading candidates. Changed scope returns a conflict.

KEYWORD uses PostgreSQL weighted title/heading/body text search and `websearch`
queries. English uses stemming; Devanagari content uses the `simple` configuration.
SEMANTIC uses exact pgvector cosine distance on the authorized index set. There is
no global approximate search followed by permission filtering.

The local profile is `intfloat/multilingual-e5-small` at revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`: 384 dimensions, query/passage prefixes,
masked mean pooling and L2 normalization. Models must be prepared explicitly.
Profiles and dimensions cannot mix. Keyword-only indexes remain usable without E5.

HYBRID takes the first 20 candidates from each path, combines ranks using
`1 / (60 + rank)`, breaks ties by UUID, considers at most 12 fused candidates,
removes overlapping near-duplicates within a document and returns at most eight.
Multiple-document results cap each document at three passages. Scores are ranking
signals, not probabilities. The chunker is
`sections-atx-320-384-overlap40-first-row-v1`.

Each answer retrieves afresh. Its evidence registry binds authorized chunks to
stored source versions and canonical Unicode code-point spans. Qwen receives
bounded evidence as untrusted data, with no tools. Structured answer validation,
exact quote mapping and a separate grounding pass precede publication. The
grounding model is fallible; exact citation validity does not establish entailment.

Current access is rechecked before generation, answer commit, history/event replay,
citation inspection, feedback and export. Retained inactive indexes support old
conversation citations until their source is removed. Markdown exports link to
the private conversation reader and include the retained source number and ID.

See [measured results](EVAL-RESULTS.md), [security boundaries](SECURITY-BOUNDARIES.md)
and [the frozen evaluation](evaluations/R8.md). No retrieval settings or frozen
labels were changed to improve the October acceptance results.
