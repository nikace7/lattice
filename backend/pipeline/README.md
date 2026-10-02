# Processing pipeline

`source_parser.py` extracts bounded UTF-8 TXT lines and native PDF text/PNG previews.
`parser_service.py` supervises two isolated subprocesses in the offline Compose
parser container. Django/Celery exchanges files through a private spool and validates
results before publication. See `docs/OPERATIONS.md` for limits and retries.
Chunking, embeddings, ranking and grounding remain future milestones.
