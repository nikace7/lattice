"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Collection, type Page, type SearchResult, type Workspace } from "@/lib/api";
import { ErrorNotice, Loading, Pagination, useResource } from "./resource";

export function Search({ workspace }: { workspace: Workspace }) {
  const [path, setPath] = useState(`/workspaces/${workspace.id}/collections?pageSize=100`);
  const collections = useResource<Page<Collection>>(path);
  const [result, setResult] = useState<SearchResult>();
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const canInspect = ["OWNER", "CURATOR"].includes(workspace.role);
  useEffect(() => () => pending.current?.abort(), []);

  function clear() {
    pending.current?.abort();
    pending.current = null;
    setBusy(false);
    setResult(undefined);
    setError(undefined);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clear();
    const form = new FormData(event.currentTarget);
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    const collection = form.get("collection");
    try {
      const data = await api<SearchResult>(`/workspaces/${workspace.id}/search`, "POST", {
        query: form.get("query"), mode: form.get("mode"), details: form.get("details") === "on",
        ...(collection ? { collectionIds: [collection] } : {}),
      }, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause : new Error("Search failed. Please retry."));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <section>
    <p className="eyebrow">Library / Search</p>
    <h1>Search your library</h1>
    <p className="muted">Find a passage, then read it in context. To ask a question with citations, open <Link href={`/w/${workspace.id}/ask`}>Ask</Link>.</p>
    <form className="upload-form" aria-label="Search sources" onSubmit={submit} onChange={clear}>
      <label htmlFor="search-query">Search words or a question</label>
      <input id="search-query" name="query" type="search" required maxLength={4000} placeholder="For example, how much notice does leave require?" />
      <details className="search-options"><summary>Search method & source scope</summary>
      <label htmlFor="search-mode">Search method</label>
      <select id="search-mode" name="mode" defaultValue="KEYWORD" aria-describedby="search-method-note">
        <option value="KEYWORD">Keyword</option><option value="SEMANTIC">Semantic</option><option value="HYBRID">Hybrid</option>
      </select>
      <p id="search-method-note" className="field-note">Keyword finds matching words. Semantic finds related meaning. Hybrid combines both. Semantic and hybrid require matching semantic indexes throughout the selected scope.</p>
      <label htmlFor="search-collection">Collection</label>
      <select id="search-collection" name="collection" key={path}>
        <option value="">All accessible collections</option>
        {collections.data?.results.map((collection) => <option key={collection.id} value={collection.id}>{collection.title}</option>)}
      </select>
      <ErrorNotice error={collections.error} retry={collections.reload} />
      {collections.data && <Pagination page={collections.data} onPage={(next) => { clear(); setPath(next); }} />}
      {canInspect && <label className="checkbox-label"><input type="checkbox" name="details" /> Show retrieval details</label>}
      </details>
      <button className="primary-button" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
    </form>
    <ErrorNotice error={error} />
    {busy && <Loading>Searching the selected sources…</Loading>}
    {result && <>
      <p role="status">{result.results.length ? `${result.results.length} source passages` : "No indexed passages found in this scope. Try different words or prepare an index in Documents."}</p>
      <ol className="search-results">
        {result.results.map((hit) => <li key={hit.chunkId}>
          <h2><Link href={`/w/${workspace.id}/documents/${hit.documentId}/passages/${hit.chunkId}`}>{hit.title}</Link></h2>
          {hit.partial && <p className="access-badge">Partial document indexed</p>}
          <p className="search-excerpt">{hit.text}</p>
          <Link href={`/w/${workspace.id}/documents/${hit.documentId}/passages/${hit.chunkId}`}>Inspect source passage ↗</Link>
        </li>)}
      </ol>
      {canInspect && result.diagnostics && <details className="search-diagnostics">
        <summary>Retrieval details</summary>
        <p>Keyword scores, cosine distances and reciprocal rank fusion scores describe ranking; they are not confidence or accuracy scores.</p>
        <p>{result.diagnostics.elapsedMs} ms · {result.diagnostics.lexical.length} keyword candidates · {result.diagnostics.vector.length} semantic candidates</p>
        <div className="search-score-table" role="region" aria-label="Ranked passage scores" tabIndex={0}>
          <table><caption>Selected passages, in result order</caption><thead><tr>
            <th scope="col">Source</th><th scope="col">Keyword rank / score</th><th scope="col">Semantic rank / distance</th><th scope="col">RRF</th>
          </tr></thead><tbody>{result.diagnostics.selected.map((row) => <tr key={row.chunkId}>
            <th scope="row">{result.results.find((hit) => hit.chunkId === row.chunkId)?.title ?? "Passage"}</th>
            <td>{row.lexicalRank ?? "—"} / {row.lexicalScore?.toFixed(4) ?? "—"}</td>
            <td>{row.vectorRank ?? "—"} / {row.cosineDistance?.toFixed(4) ?? "—"}</td>
            <td>{row.rrf.toFixed(5)}</td>
          </tr>)}</tbody></table>
        </div>
        <p className="field-note">Corpus: {result.diagnostics.corpusHash}<br />Profile: {result.diagnostics.profileHash}</p>
      </details>}
    </>}
  </section>;
}
