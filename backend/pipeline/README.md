# Processing pipeline

`source_parser.py` extracts bounded UTF-8 TXT/Markdown lines, native PDF text/PNG
previews and DOCX body paragraphs/table cells. Markdown stays literal; DOCX XML
uses defusedxml and bounded ZIP reads without resolving external relationships.
`parser_service.py` supervises two isolated subprocesses in the offline Compose
parser container. Django/Celery exchanges files through a private spool and validates
results before publication. See `docs/OPERATIONS.md` for limits and retries.
Chunking, embeddings, ranking and grounding remain future milestones.

PDF pages with fewer than 20 native non-whitespace characters use Tesseract with
English, Nepali or both languages. OCR words become Unicode-preserving lines with
normalized boxes and engine confidence. Every OCR, empty or failed page requires
review. Per-page failures preserve successful pages; reviewers must exclude failed
or empty pages and supply a reason. Acceptance records actor/time and exclusions,
but does not create a searchable index. Future indexing must honor excluded pages.
Tesseract runs only in the parser image with a bounded deadline and one OpenMP thread;
the supervisor kills the entire job process group after completion or timeout.

OCR reference: [Tesseract command-line usage and TSV output](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

References: [WordprocessingML structure](https://learn.microsoft.com/en-us/office/open-xml/word/structure-of-a-wordprocessingml-document)
and [Python XML security guidance](https://docs.python.org/3.12/library/xml.html#xml-vulnerabilities).
