# Processing pipeline

`source_parser.py` extracts bounded UTF-8 TXT/Markdown lines, native PDF text/PNG
previews and DOCX body paragraphs/table cells. Markdown stays literal; DOCX XML
uses defusedxml and bounded ZIP reads without resolving external relationships.
`parser_service.py` supervises two isolated subprocesses in the offline Compose
parser container. Django/Celery exchanges files through a private spool and validates
results before publication. See `docs/OPERATIONS.md` for limits and retries.
Chunking, embeddings, ranking and grounding remain future milestones.

References: [WordprocessingML structure](https://learn.microsoft.com/en-us/office/open-xml/word/structure-of-a-wordprocessingml-document)
and [Python XML security guidance](https://docs.python.org/3.12/library/xml.html#xml-vulnerabilities).
