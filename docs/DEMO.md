# Lattice demo and handoff

R1–R7 features and R8 offline evidence are implemented. Full-stack acceptance is
still pending. This walkthrough keeps illustrative UI fixtures, measured retrieval
and a future live application demonstration clearly identified.

## Review today without Docker

1. Read [the frozen evaluation](evaluations/R8.md): 24 fictional documents, 25 source
   versions, 40 development and 40 held-out cases, actual model/profile and counts.
2. Run its `--validate-only` command. Optionally reproduce offline E5 retrieval with
   prepared model files. The command never modifies application data.
3. Build and run the UI checks on the existing host:

   ```sh
   pnpm build
   pnpm --filter @lattice/web exec playwright test --config playwright.reader.config.ts
   ```

   This starts only a production web server on loopback port 4413 and mocks every
   API request. It demonstrates source highlight/focus, mobile navigation, resizing,
   evaluation inspection and automated accessibility at 360/768/1200/1440px.
   The answer and deliberately incomplete comparison are **UI test data**, not
   outputs from Qwen or the R8 benchmark.

## Preserved UI evidence

Captured on 8 October 2026 from the production build with mocked APIs. Reader
screens include a visible demonstration label; evaluation screenshots identify
their comparison as a test fixture. None establishes live backend behavior.

![Desktop reader with older-version citation](assets/r8/reader-desktop.png)

![Mobile reader with exact highlight and back action](assets/r8/reader-mobile.png)

![Desktop evaluation case inspection using deliberately incomplete UI test data](assets/r8/evaluation-desktop.png)

![Mobile evaluation case inspection using UI test data](assets/r8/evaluation-mobile.png)

## Live walkthrough after infrastructure validation

This is a **proposed script, not an observed successful run**. Start with a dedicated
disposable demo database and storage root containing no real documents. Automated
`seed_demo` and guarded `demo:reset` do not exist yet; do not substitute an unguarded
database or storage deletion. Existing fixtures can be uploaded through the UI.

1. Follow README setup, start Docker, apply migrations, rebuild API/workers/parser,
   and run real tests. Preserve the independent tombstone journal before any restore.
2. Register fictional owner, curator and viewer accounts using local Mailpit. Create
   Cedar Studio (workspace A) and Birch Studio (workspace B). The frozen `a-member`
   persona maps to the application's VIEWER role; fixture roles are scope labels,
   not an import of production grants.
3. In A, create Handbook (workspace-readable), Projects (restricted, curator grant)
   and Finance (restricted, owner-only). In B, create a separate Handbook. Follow
   [the manifest](../fixtures/evals/r8-v1.json) when assigning documents; matching
   titles such as Leave requests must remain in different workspaces.
4. Upload the 25 [source files](../fixtures/corpus/r8-v1) as 24 documents: upload
   `leave-v1.txt` first, index it, then use Replace with `leave-v2.txt`. The other
   files are initial versions. Extract/review and prepare indexes. Review the
   scanned `drill-v1.pdf` before acceptance; compare actual OCR to its manual reference.
5. Use keyword search in retrieval-only mode. For semantic/hybrid and answers,
   explicitly prepare E5 and Qwen as described in operations, select local mode,
   and reindex the workspace coherently. No cloud key is needed. Answer controls
   must explain unavailable generation while the default retrieval-only mode remains.
6. Ask the leave-notice question and inspect its exact v2 citation. Ask an unsupported
   question and a conflicting-policy question; record actual statuses, evidence and
   token use. Never present an authored expected answer as a model result.
7. As viewer/curator, test denied collections, same-title B documents, forged scope
   and direct source IDs. Revoke access while a turn runs and while reading history.
   Confirm real retrieval, source and stored-answer denial; fixture filtering is insufficient.
8. Replace an active source, inspect a retained citation, cancel/retry reindex, then
   delete a demo document and test history unavailability and physical purge. Exercise
   crash/replay/race and tombstone-aware restore checks before erasure claims.
9. As owner, open Evaluations. R4 is document-group development evidence; R8 is
   frozen exact-span offline evidence. Both are synthetic artifacts shared across
   owner diagnostics, not measurements of this workspace's uploaded documents.

Do not publish screenshots containing real documents, email, storage paths or
credentials. A future live demo/recording must show its actual model/corpus version
and keep unexpected outcomes rather than replacing them with fixture output.

## Completion record still required

Record a fresh checkout/machine setup with tool versions and commands; full PostgreSQL
tests and actual ingestion/browser output; lexical/vector/hybrid frozen results;
human-labelled answer/citation/abstention/conflict counts; migration, revocation,
race and restore outcomes; and a live demo recording. Until then, the project is
an implemented application with limited measured evidence, not acceptance-complete.
