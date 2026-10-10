# Lattice: a private source workspace

Lattice turns team documents into searchable evidence and private, cited answers.
Its main engineering constraint is preserving collection access and exact source
versions across ingestion, search, generation, replacement and deletion.

The implementation combines Django/PostgreSQL/pgvector, bounded Celery queues,
an offline PDF/DOCX/TXT/Markdown parser and local E5/Qwen models with a Next.js
reader. It stores originals privately, distinguishes extracted from searchable
documents, requires review for scans/partial extraction, and retains old citations
when a replacement becomes current. An independent deletion journal survives a
database backup and is replayed on restore.

The interface uses a reading-room palette, locally served Manrope and Source Serif
4, clear document rows, restrained motion and a source panel with exact highlights.
Keyboard source return, Nepali composition, mobile navigation, search scope and
private conversation controls are exercised by automated checks. Actual live
screenshots and the walkthrough are listed in [the demo guide](DEMO.md).

On 10 October 2026, Docker acceptance exercised the real database, Redis workers,
parser, OCR, pinned models, backup restore and a fresh checkout with new volumes.
The complete frozen suite has 80 actual question attempts; one development worker
attempt failed and remains in the report. SQL hybrid retrieval found every required
gold span in this small authored corpus. Every emitted citation passed automatic
exact-source checks. These results do not imply general answer accuracy.

The main limitation is answer quality: the small local model sometimes abstains
despite relevant evidence and does not consistently label conflicts. Human factual
claim review remains open. A development-only prompt clarification failed to improve
six diagnostics and was discarded before the held-out run. The original results,
failed attempt and blank human-review templates are preserved. See
[results and acceptance limits](EVAL-RESULTS.md) before using this as quality evidence.
