"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Collection, type DocumentSource, type Page, type SourceBlock, type Workspace } from "@/lib/api";
import { ErrorNotice, Loading, Pagination, useAction, useResource } from "./resource";

const states: Record<string, string> = {
  QUEUED: "Queued for extraction", EXTRACTING: "Extracting text",
  EXTRACTED: "Text extracted", NEEDS_REVIEW: "Needs review", FAILED: "Extraction failed",
};

export function Documents({ workspace, documentId }: { workspace: Workspace; documentId?: string }) {
  return documentId ? <SourceViewer key={documentId} workspace={workspace} id={documentId} /> : <DocumentList workspace={workspace} />;
}

function DocumentList({ workspace }: { workspace: Workspace }) {
  const [collectionPath, setCollectionPath] = useState(`/workspaces/${workspace.id}/collections?pageSize=100`);
  const collections = useResource<Page<Collection>>(collectionPath);
  const [collectionId, setCollectionId] = useState("");
  const base = `/workspaces/${workspace.id}/documents${collectionId ? `?collectionId=${collectionId}` : ""}`;
  const [cursor, setCursor] = useState<{ base: string; path: string }>();
  const documents = useResource<Page<DocumentSource>>(cursor?.base === base ? cursor.path : base);
  const writable = collections.data?.results.filter((collection) => collection.canWrite) ?? [];
  const pending = documents.data?.results.some((document) => ["QUEUED", "EXTRACTING"].includes(document.state));
  useEffect(() => {
    if (!pending) return;
    const timer = setTimeout(documents.reload, 2500);
    return () => clearTimeout(timer);
  }, [pending, documents.data, documents.reload]);
  return <section>
    <p className="eyebrow">YOUR SOURCES, CLOSE AT HAND</p>
    <div className="section-heading"><h1>Documents</h1><button onClick={documents.reload}>Refresh documents</button></div>
    <p className="muted">Upload PDF, Word, Markdown or plain text, then inspect the original evidence. Search and answers come next.</p>
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
          <span><strong>{document.title}</strong><small>{states[document.state]} · source version 1 · {Math.ceil(document.byteSize / 1024)} KiB</small></span>
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
    <p id="upload-limits" className="field-note">PDF, DOCX, TXT or Markdown. Up to 25 MiB, 100 PDF pages. Text files must use UTF-8. Files stay private to this collection. Scanned pages need OCR, which is coming next.</p>
    <ErrorNotice error={action.error} />
    <button className="primary-button" disabled={action.busy}>{action.busy ? "Uploading and queuing…" : "Upload document"}</button>
  </form>;
}

function SourceViewer({ workspace, id }: { workspace: Workspace; id: string }) {
  const document = useResource<DocumentSource>(`/documents/${id}`);
  const action = useAction();
  const state = document.data?.state;
  useEffect(() => {
    if (!state || !["QUEUED", "EXTRACTING"].includes(state)) return;
    const timer = setTimeout(document.reload, 2500);
    return () => clearTimeout(timer);
  }, [state, document.data, document.reload]);
  return <section>
    <Link href={`/w/${workspace.id}/documents`}>← All documents</Link>
    <ErrorNotice error={document.error} retry={document.reload} />
    {!document.data && !document.error && <Loading>Opening the source…</Loading>}
    {document.data && <>
      <p className="eyebrow">SOURCE VERSION 1</p>
      <h1 className="source-title">{document.data.title}</h1>
      <p className="source-status" role="status">{states[document.data.state]}{["EXTRACTED", "NEEDS_REVIEW"].includes(document.data.state) ? " · Not indexed for search yet" : ""}</p>
      <div className="source-actions">
        <a href={`/api/v1/sources/${document.data.sourceId}/original`} download>Download original</a>
        <button onClick={document.reload}>Refresh source</button>
        {document.data.canWrite && (document.data.retryable || ["QUEUED", "EXTRACTING"].includes(document.data.state)) && <button disabled={action.busy} onClick={() => void action.run(async () => {
          await api(`/documents/${id}/retry`, "POST", { expectedRevision: document.data!.revision });
          document.reload();
        })}>Retry extraction</button>}
      </div>
      {document.data.error && <p className="error-notice" role="alert">{document.data.error}</p>}
      <ErrorNotice error={action.error} />
      {document.data.warnings.length > 0 && <div className="source-warnings"><h2>Review needed</h2><ul>{document.data.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
      {["QUEUED", "EXTRACTING"].includes(document.data.state) && <p>Extraction runs in the background. This page refreshes automatically. A stuck job can be retried after 10 minutes.</p>}
      {["EXTRACTED", "NEEDS_REVIEW"].includes(document.data.state) && <SourceContent document={document.data} />}
    </>}
  </section>;
}

type Locator = { line?: number; page?: number; bbox?: number[]; paragraph?: number; table?: number; row?: number; cell?: number; headingPath?: string[] };

function locationLabel(block: SourceBlock) {
  const location = block.locator as Locator;
  if (location.page) return `Page ${location.page}`;
  if (location.table) return `Table ${location.table}, row ${location.row}, cell ${location.cell} · Paragraph ${location.paragraph}`;
  if (location.paragraph) return `Paragraph ${location.paragraph}`;
  return `Line ${location.line}`;
}

function SourceContent({ document }: { document: DocumentSource }) {
  const [page, setPage] = useState(1);
  const [panel, setPanel] = useState("text");
  const [selected, setSelected] = useState<SourceBlock>();
  const selectedButton = useRef<HTMLButtonElement | null>(null);
  const base = `/sources/${document.sourceId}/blocks${document.kind === "PDF" ? `?page=${page}` : ""}`;
  const [cursor, setCursor] = useState<{ base: string; path: string }>();
  const blocks = useResource<Page<SourceBlock>>(cursor?.base === base ? cursor.path : base);
  const box = (selected?.locator as Locator | undefined)?.bbox;
  const pdf = document.kind === "PDF";
  return <>
    {pdf && <div className="source-actions">
      <label htmlFor="physical-page">Physical page</label>
      <select id="physical-page" value={page} onChange={(event) => { setPage(Number(event.target.value)); setSelected(undefined); }}>
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
      {pdf && <section className={`page-panel ${panel === "text" ? "mobile-hidden" : ""}`} aria-label="Original page preview">
        <h2>Source page {page}</h2>
        <p className="field-note">Original page image. Native extraction can misread complex layouts; compare it with the text.</p>
        <div className="pdf-page">
          {/* Same-origin, permission-checked image; Next image optimization must not cache private sources. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/v1/sources/${document.sourceId}/pages/${page}`} alt={`Original page ${page} of ${document.title}. Extracted text is available alongside this image.`} />
          {box && <div className="source-highlight" role="img" aria-label="Selected source passage" style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }} />}
        </div>
        <button className="source-tab" onClick={() => { setPanel("text"); requestAnimationFrame(() => selectedButton.current?.focus()); }}>Back to extracted text</button>
      </section>}
    </div>
  </>;
}
