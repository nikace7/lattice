# Processing pipeline

`source_parser.py` extracts bounded UTF-8 TXT/Markdown lines, native PDF text/PNG
previews and DOCX body paragraphs/table cells. Markdown stays literal; DOCX XML
uses defusedxml and bounded ZIP reads without resolving external relationships.
`parser_service.py` supervises two isolated subprocesses in the offline Compose
parser container. Django/Celery exchanges files through a private spool and validates
results before publication. See `docs/OPERATIONS.md` for limits and retries.
`chunking.py` preserves exact block spans while packing tokenizer-bounded sections;
`embedding.py` runs pinned, offline CPU E5 inference. Ranking and grounding remain
future milestones. `pnpm models:prepare` explicitly downloads the model and writes
a checksum/profile manifest; `pnpm models:check` compares actual inference with
reference pooling and checks English/Nepali chunk coverage.

PDF pages with fewer than 20 native non-whitespace characters use Tesseract with
English, Nepali or both languages. OCR words become Unicode-preserving lines with
normalized boxes and engine confidence. Every OCR, empty or failed page requires
review. Per-page failures preserve successful pages; reviewers must exclude failed
or empty pages and supply a reason. Acceptance records actor/time and exclusions,
but does not itself create an index. Index preparation honors excluded pages and
requires acceptance before processing warnings. Word omissions can also be accepted
with a review note and no invented page exclusions.
Tesseract runs only in the parser image with a bounded deadline and one OpenMP thread;
the supervisor kills the entire job process group after completion or timeout.
Removing a cancelled job's spool also stops its owned process group. The worker
checks cancellation/attempt ownership while waiting and renews a 90-second database
lease every 15 seconds. Beat requeues expired jobs with new attempts up to three times;
publication requires the current attempt, extracting state and an unexpired lease.

OCR reference: [Tesseract command-line usage and TSV output](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html).

E5 procedure/reference: [pinned model card](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/README.md).

References: [WordprocessingML structure](https://learn.microsoft.com/en-us/office/open-xml/word/structure-of-a-wordprocessingml-document)
and [Python XML security guidance](https://docs.python.org/3.12/library/xml.html#xml-vulnerabilities).
