"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Collection, type DocumentSource, type Page, type SourceBlock, type Workspace } from "@/lib/api";
import { ErrorNotice, Loading, Pagination, useAction, useResource } from "./resource";

const states: Record<string, string> = {
  QUEUED: "Queued for extraction", EXTRACTING: "Extracting text",
  EXTRACTED: "Text extracted", NEEDS_REVIEW: "Needs review", FAILED: "Extraction failed",
  REVIEWED: "Extraction review accepted",
  CANCELLED: "Extraction cancelled",
};

export function Documents({ workspace, documentId, chunkId }: { workspace: Workspace; documentId?: string; chunkId?: string }) {
  return documentId ? <SourceViewer key={`${documentId}:${chunkId ?? ""}`} workspace={workspace} id={documentId} chunkId={chunkId} /> : <DocumentList workspace={workspace} />;
}

function DocumentList({ workspace }: { workspace: Workspace }) {
  const [collectionPath, setCollectionPath] = useState(`/workspaces/${workspace.id}/collections?pageSize=100`);
  const collections = useResource<Page<Collection>>(collectionPath);
  const [collectionId, setCollectionId] = useState("");
  const base = `/workspaces/${workspace.id}/documents${collectionId ? `?collectionId=${collectionId}` : ""}`;
  const [cursor, setCursor] = useState<{ base: string; path: string }>();
  const documents = useResource<Page<DocumentSource>>(cursor?.base === base ? cursor.path : base);
  const writable = collections.data?.results.filter((collection) => collection.canWrite) ?? [];
  const pending = documents.data?.results.some((document) => ["QUEUED", "EXTRACTING"].includes(document.state) || ["QUEUED", "CHUNKING", "EMBEDDING"].includes(document.index?.state ?? ""));
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(documents.reload, 2500);
    return () => clearTimeout(timer);
  }, [pending, documents.data, documents.reload]);
  return <section>
    <p className="eyebrow">YOUR SOURCES, CLOSE AT HAND</p>
    <div className="section-heading"><h1>Documents</h1><button onClick={documents.reload}>Refresh documents</button></div>
    <p className="muted">Upload PDF, Word, Markdown or plain text, then prepare an index to search the original evidence.</p>
    <ErrorNotice error={collections.error} retry={collections.reload} />
    {writable.length > 0 && <UploadForm collections={writable} workspace={workspace} />}
    {collections.data && <>
      <label htmlFor="document-filter">Filter by collection</label>
      <select id="document-filter" value={collectionId} onChange={(event) => setCollectionId(event.target.value)}>
        <option value="">All accessible collections</option>
        {collections.data.results.map((collection) => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
      </select>
      <Pagination page={collections.data} onPage={setCollectionPath} />
    </>}
    <ErrorNotice error={documents.error} retry={documents.reload} />
    {!documents.data && !documents.error && <Loading>Finding your documents…</Loading>}
    {documents.data && <>
      {documents.data.results.length ? <div className="document-list">
        {documents.data.results.map((document) => <Link className="workspace-row" key={document.id} href={`/w/${workspace.id}/documents/${document.id}`}>
          <span className="access-badge">{document.kind}</span>
          <span><strong>{document.title}</strong><small>{states[document.state]} · {document.index?.active ? "Index ready" : "Not indexed"} · source version 1 · {Math.ceil(document.byteSize / 1024)} KiB</small></span>
          <span aria-hidden="true">↗</span>
        </Link>)}
      </div> : <div className="empty-library"><h2>No documents here yet.</h2><p>{writable.length ? "Add your first source using the form above." : "Ask a curator to add documents, or create a collection if you are an owner."}</p><Link href={`/w/${workspace.id}/collections`}>View collections</Link></div>}
      <Pagination page={documents.data} onPage={(path) => setCursor({ base, path })} />
    </>}
  </section>;
}

function UploadForm({ collections, workspace }: { collections: Collection[]; workspace: Workspace }) {
  const action = useAction();
  const uploadId = useRef<string | null>(null);
  const router = useRouter();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    uploadId.current ??= crypto.randomUUID();
    values.set("uploadId", uploadId.current);
    const collection = values.get("collection");
    values.delete("collection");
    void action.run(async () => {
      const document = await api<DocumentSource>(`/collections/${collection}/documents`, "POST", values);
      router.push(`/w/${workspace.id}/documents/${document.id}`);
    });
  }
  return <form className="upload-form" onSubmit={submit} aria-label="Upload a document">
    <h2>Add a source</h2>
    <label htmlFor="upload-collection">Destination collection</label>
    <select id="upload-collection" name="collection" disabled={action.busy} onChange={() => { uploadId.current = null; }}>
      {collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
    </select>
    <label htmlFor="source-file">Document file</label>
    <input id="source-file" name="file" type="file" accept=".pdf,.docx,.txt,.md" required disabled={action.busy} onChange={() => { uploadId.current = null; }} aria-describedby="upload-limits" />
    <p id="upload-limits" className="field-note">PDF, DOCX, TXT or Markdown. Up to 25 MiB, 100 PDF pages. Text files must use UTF-8. Files stay private to this collection.</p>
    <label htmlFor="ocr-language">Scanned PDF language</label>
    <select id="ocr-language" name="ocrLanguage" disabled={action.busy} onChange={() => { uploadId.current = null; }}>
      <option value="eng">English</option><option value="nep">Nepali</option><option value="eng+nep">English + Nepali</option>
    </select>
    <p className="field-note">Pages with little native text use OCR and require review. Other file types ignore this setting.</p>
    <ErrorNotice error={action.error} />
    <button className="primary-button" disabled={action.busy}>{action.busy ? "Uploading and queuing…" : "Upload document"}</button>
  </form>;
}

function SourceViewer({ workspace, id, chunkId }: { workspace: Workspace; id: string; chunkId?: string }) {
  const document = useResource<DocumentSource>(`/documents/${id}`);
  const action = useAction();
  const state = document.data?.state;
  const indexState = document.data?.index?.state;
  useEffect(() => {
    if (!["QUEUED", "EXTRACTING"].includes(state ?? "") && !["QUEUED", "CHUNKING", "EMBEDDING"].includes(indexState ?? "")) return;
    const timer = setTimeout(document.reload, 2500);
    return () => clearTimeout(timer);
  }, [state, indexState, document.data, document.reload]);
  return <section>
    <Link href={`/w/${workspace.id}/documents`}>← All documents</Link>
    <ErrorNotice error={document.error} retry={document.reload} />
    {!document.data && !document.error && <Loading>Opening the source…</Loading>}
    {document.data && <>
      <p className="eyebrow">SOURCE VERSION 1</p>
      <h1 className="source-title">{document.data.title}</h1>
      <p className="source-status" role="status">{states[document.data.state]}</p>
      {["EXTRACTED", "REVIEWED"].includes(document.data.state) && <IndexStatus document={document.data} reload={document.reload} />}
      <div className="source-actions">
        <a href={`/api/v1/sources/${document.data.sourceId}/original`} download>Download original</a>
        <button onClick={document.reload}>Refresh source</button>
        {document.data.canWrite && document.data.retryable && <button disabled={action.busy} onClick={() => void action.run(async () => {
          await api(`/documents/${id}/retry`, "POST", { expectedRevision: document.data!.revision });
          document.reload();
        })}>Retry extraction</button>}
        {document.data.canWrite && ["QUEUED", "EXTRACTING"].includes(document.data.state) && <button disabled={action.busy} onClick={() => void action.run(async () => {
          await api(`/documents/${id}/cancel`, "POST", { expectedRevision: document.data!.revision });
          document.reload();
        })}>Cancel extraction</button>}
      </div>
      {document.data.error && <p className="error-notice" role="alert">{document.data.error}</p>}
      <ErrorNotice error={action.error} />
      {document.data.warnings.length > 0 && <div className="source-warnings"><h2>Extraction warnings</h2><ul>{document.data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
      {document.data.state === "REVIEWED" && <div className="source-warnings"><h2>{document.data.excludedPages.length ? "Partial extraction accepted" : "Extraction accepted"}</h2><p>{document.data.kind === "DOCX" ? "Extracted Word content accepted; the listed omissions remain excluded." : document.data.excludedPages.length ? `Excluded pages: ${document.data.excludedPages.join(", ")}.` : "All pages included."}</p><p>Review note: {document.data.reviewReason}</p></div>}
      {document.data.canWrite && ["PDF", "DOCX"].includes(document.data.kind) && document.data.state === "NEEDS_REVIEW" && <ReviewForm key={document.data.revision} document={document.data} onAccepted={document.reload} />}
      {["QUEUED", "EXTRACTING"].includes(document.data.state) && <p>Extraction runs in the background. This page refreshes automatically. Interrupted jobs recover automatically up to three times; retry becomes available after 90 seconds without an update.</p>}
      {document.data.state === "CANCELLED" && <p>Extraction was cancelled. The original file is preserved; retry to start a new attempt.</p>}
      {["EXTRACTED", "NEEDS_REVIEW", "REVIEWED"].includes(document.data.state) && <SourceContent document={document.data} chunkId={chunkId} fullDocumentHref={`/w/${workspace.id}/documents/${id}`} />}
    </>}
  </section>;
}

type Locator = { line?: number; page?: number; bbox?: number[]; paragraph?: number; table?: number; row?: number; cell?: number; headingPath?: string[] };

function IndexStatus({ document, reload }: { document: DocumentSource; reload: () => void }) {
  const action = useAction();
  const index = document.index;
  const running = ["QUEUED", "CHUNKING", "EMBEDDING"].includes(index?.state ?? "");
  const labels: Record<string, string> = { QUEUED: "Queued for indexing", CHUNKING: "Preparing source passages", EMBEDDING: "Preparing search index", READY: "Index ready", FAILED: "Indexing failed", CANCELLED: "Indexing cancelled" };
  function submit(cancel = false) {
    void action.run(async () => {
      await api(`/documents/${document.id}/${cancel ? "cancel-index" : "index"}`, "POST", { expectedRevision: document.revision });
      reload();
    });
  }
  return <div className="source-warnings">
    <p role="status">{index ? labels[index.state] : "Not indexed yet"}{index?.active ? ` · ${index.semantic ? "Semantic" : "Keyword-only"} index${document.excludedPages.length ? " · Partial document indexed" : ""}` : ""}</p>
    <p className="field-note">Ready indexes are available in Search. Preparing an index preserves references to the source passages.</p>
    {index?.error && <p className="error-notice" role="alert">{index.error}</p>}
    <ErrorNotice error={action.error} />
    {document.canWrite && (!index || index.canRetry) && <button disabled={action.busy} onClick={() => submit()}>{index ? "Retry indexing" : "Prepare search index"}</button>}
    {document.canWrite && running && <button disabled={action.busy} onClick={() => submit(true)}>Cancel indexing</button>}
  </div>;
}
type PageReport = { page: number; status: string; preview: boolean; confidence: number | null; language: string; engine: string };

function ReviewForm({ document, onAccepted }: { document: DocumentSource; onAccepted: () => void }) {
  const reports = document.pageReports as PageReport[];
  const required = reports.filter((page) => ["FAILED", "EMPTY"].includes(page.status)).map((page) => page.page);
  const [excluded, setExcluded] = useState(required);
  const action = useAction();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    void action.run(async () => {
      await api(`/documents/${document.id}/accept-review`, "POST", { expectedRevision: document.revision, excludedPages: excluded, reason: values.get("reason") });
      onAccepted();
    });
  }
  return <form className="upload-form" onSubmit={submit} aria-label="Review extraction">
    <h2>Review extraction</h2>
    <p>{document.kind === "PDF" ? "Compare the text with the source below. Failed or empty pages must be excluded." : "Compare the extracted text with the original Word file. Accepting acknowledges the listed omissions; only the extracted content will be indexed."}</p>
    {reports.length > 0 && <fieldset disabled={action.busy}><legend>Pages to exclude</legend>
      {reports.map((page) => <label className="checkbox-label" key={page.page}><input type="checkbox" checked={excluded.includes(page.page)} disabled={required.includes(page.page)} onChange={(event) => setExcluded(event.target.checked ? [...excluded, page.page] : excluded.filter((n) => n !== page.page))} /> Exclude page {page.page} ({page.status.toLowerCase()}{required.includes(page.page) ? "; required" : ""})</label>)}
    </fieldset>}
    <label htmlFor="review-reason">Review note</label>
    <textarea id="review-reason" name="reason" required maxLength={1000} disabled={action.busy} />
    <ErrorNotice error={action.error} />
    <button className="primary-button" disabled={action.busy || (reports.length > 0 && excluded.length === reports.length)}>{action.busy ? "Saving review…" : "Accept extraction"}</button>
    {reports.length > 0 && excluded.length === reports.length && <p>All pages are excluded. Upload a corrected file to continue.</p>}
  </form>;
}

function locationLabel(block: SourceBlock) {
  const location = block.locator as Locator;
  if (location.page) return `Page ${location.page}`;
  if (location.table) return `Table ${location.table}, row ${location.row}, cell ${location.cell} · Paragraph ${location.paragraph}`;
  if (location.paragraph) return `Paragraph ${location.paragraph}`;
  return `Line ${location.line}`;
}

function SourceContent({ document, chunkId, fullDocumentHref }: { document: DocumentSource; chunkId?: string; fullDocumentHref: string }) {
  const [page, setPage] = useState(1);
  const [panel, setPanel] = useState("text");
  const [selected, setSelected] = useState<SourceBlock>();
  const selectedButton = useRef<HTMLButtonElement | null>(null);
  const base = `/sources/${document.sourceId}/blocks${chunkId ? `?chunkId=${chunkId}` : document.kind === "PDF" ? `?page=${page}` : ""}`;
  const [cursor, setCursor] = useState<{ base: string; path: string }>();
  const blocks = useResource<Page<SourceBlock>>(cursor?.base === base ? cursor.path : base);
  const box = (selected?.locator as Locator | undefined)?.bbox;
  const pdf = document.kind === "PDF";
  const shownPage = chunkId ? (selected?.locator as Locator | undefined)?.page ?? (blocks.data?.results[0]?.locator as Locator | undefined)?.page ?? 1 : page;
  const report = (document.pageReports as PageReport[]).find((item) => item.page === shownPage);
  return <>
    {chunkId && <p className="source-warnings">Source blocks for the selected search passage. <Link href={fullDocumentHref}>Open the full document</Link></p>}
    {pdf && <div className="source-actions">
      <label htmlFor="physical-page">Physical page</label>
      <select id="physical-page" value={shownPage} disabled={!!chunkId} onChange={(event) => { setPage(Number(event.target.value)); setSelected(undefined); }}>
        {Array.from({ length: document.pageCount }, (_, index) => <option key={index} value={index + 1}>{index + 1} of {document.pageCount}</option>)}
      </select>
      <button className="source-tab" aria-pressed={panel === "text"} onClick={() => setPanel("text")}>Extracted text</button>
      <button className="source-tab" aria-pressed={panel === "page"} onClick={() => setPanel("page")}>Source page</button>
    </div>}
    <div className={`source-reader ${pdf ? "pdf-reader" : ""}`}>
      <section className={`extracted-panel ${panel === "page" ? "mobile-hidden" : ""}`} aria-label="Extracted text">
        <h2>Extracted text</h2><p className="field-note">Select a passage to inspect its source location. Text is preserved without changing Unicode characters.</p>
        {document.kind === "MD" && <p className="field-note">Markdown is shown as source text. HTML, links and remote images stay inactive.</p>}
        {document.kind === "DOCX" && <p className="field-note">Word references use body paragraph and table-cell positions. Download the original to compare layout and formatting.</p>}
        {report?.status === "OCR" && <p className="field-note">OCR language: {report.language}. Engine confidence: {report.confidence ?? "unavailable"}{report.confidence !== null ? "%" : ""}. This is not a measured accuracy score; compare the text with the page.</p>}
        {document.excludedPages.includes(page) && pdf && <p className="source-warnings">This page is excluded from the accepted extraction. Its original text remains available for inspection.</p>}
        <ErrorNotice error={blocks.error} retry={blocks.reload} />
        {!blocks.data && !blocks.error && <Loading>Loading source passages…</Loading>}
        {blocks.data && <>
          {!blocks.data.results.length && <p>No text was extracted from this page.</p>}
          <div className="source-passages">
            {blocks.data.results.map((block) => <button id={`block-${block.id}`} className="source-passage" aria-pressed={selected?.id === block.id} key={block.id} onClick={(event) => { setSelected(block); selectedButton.current = event.currentTarget; }}>
              <small>{locationLabel(block)}</small>
              {(block.locator as Locator).headingPath?.length ? <small>{(block.locator as Locator).headingPath!.join(" › ")}</small> : null}
              <span>{block.text}</span>
            </button>)}
          </div>
          <Pagination page={blocks.data} onPage={(path) => { setCursor({ base, path }); setSelected(undefined); }} />
        </>}
        {selected && <p role="status">Selected {locationLabel(selected)}. {pdf ? "The passage is highlighted on the source page." : "The selected passage retains its original source reference."}</p>}
      </section>
      {pdf && (!chunkId || (blocks.data && blocks.data.results.length > 0)) && <section className={`page-panel ${panel === "text" ? "mobile-hidden" : ""}`} aria-label="Original page preview">
        <h2>Source page {shownPage}</h2>
        <p className="field-note">Original page image. Native extraction can misread complex layouts; compare it with the text.</p>
        {report && !report.preview ? <p>Preview unavailable for this page. Download the original to inspect it.</p> : <div className="pdf-page">
          {/* Same-origin, permission-checked image; Next image optimization must not cache private sources. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/v1/sources/${document.sourceId}/pages/${shownPage}`} alt={`Original page ${shownPage} of ${document.title}. Extracted text is available alongside this image.`} />
          {box && <div className="source-highlight" role="img" aria-label="Selected source passage" style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }} />}
        </div>}
        <button className="source-tab" onClick={() => { setPanel("text"); requestAnimationFrame(() => selectedButton.current?.focus()); }}>Back to extracted text</button>
      </section>}
    </div>
  </>;
}
