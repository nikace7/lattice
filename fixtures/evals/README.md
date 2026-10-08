# Evaluation fixtures

`r4-development.json` is the small, document-group development check. Its recorded
offline E5 result is separate from the frozen R8 suite.

`r8-v1.json` freezes 24 original fictional documents / 25 versions and 80 labelled
cases. Each 40-question split contains 20 direct, 5 cross-document, 5 unanswerable,
3 conflict, 3 Nepali and 4 access cases. Topic/fact templates do not cross splits.
Gold records identify document, exact source version, canonical block and Unicode
code-point offsets/quote. Required answer facts, abstention, caller persona and
permitted collection scope are authored expectations, not model answers.

`r8-v1.lock.json` pins the whole manifest, including source file SHA-256 values.
Validation fails on altered labels, quote/version/scope errors or file changes.
Do not regenerate the lock merely to accept a failed check. New source replacements
or label changes require a deliberately reviewed new corpus/suite version.

See [R8 evidence](../../docs/evaluations/R8.md) for observed counts, definitions,
reproduction commands and pending acceptance gates. The real offline report retains
all cases; unanswerable/denied cases have `fullEvidence: null`, and abstention and
answer measurements remain unmeasured. No application data is seeded or exported.
