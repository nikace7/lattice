"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, type DocumentSource, type Page, type Workspace } from "@/lib/api";
import type { components } from "@/lib/api.generated";
import { ErrorNotice, Pagination, useAction, useResource } from "./resource";

type Version = components["schemas"]["VersionData"];
type Batch = components["schemas"]["ReindexData"];
type Quotas = components["schemas"]["Quotas"];

export function DocumentLifecycle({ document, workspace, selectSource, reload }: {
  document: DocumentSource; workspace: Workspace; selectSource: (id: string) => void; reload: () => void;
}) {
  const base = `/documents/${document.id}/versions`;
  const [path, setPath] = useState(base);
  const versions = useResource<Page<Version>>(path);
  const action = useAction();
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  function remove(source?: string) {
    void action.run(async () => {
      await api(`/documents/${document.id}/${source ? `versions/${source}/purge` : "delete"}`, "POST", { expectedRevision: document.revision });
      if (source) { setConfirm(""); reload(); }
      else router.push(`/w/${workspace.id}/documents`);
    });
  }
  return <details className="source-warnings">
    <summary>Source versions and retention</summary>
    <p>Older versions keep their exact citation references until an owner removes them.</p>
    <ErrorNotice error={versions.error} retry={versions.reload} />
    {versions.data && <>
      <ul>{versions.data.results.map((version) => <li key={version.id}>
        <button disabled={action.busy || version.id === document.sourceId} onClick={() => selectSource(version.id)}>Version {version.number}: {version.filename}</button>
        {version.current && " · Current searchable version"}{version.pending && " · Latest upload"}
        {workspace.role === "OWNER" && !version.current && !version.pending && <button disabled={action.busy} onClick={() => setConfirm(version.id)}>Remove retained version {version.number}</button>}
      </li>)}</ul>
      <Pagination page={versions.data} onPage={setPath} />
    </>}
    {document.canWrite && <button disabled={action.busy} onClick={() => setConfirm("document")}>Delete document</button>}
    {confirm && <div role="group" aria-label="Confirm deletion">
      <p>{confirm === "document" ? "Delete this document and all its versions?" : "Permanently remove this retained version?"} Dependent answers become unavailable immediately. Stored files and text are purged in the background.</p>
      <button disabled={action.busy} onClick={() => remove(confirm === "document" ? undefined : confirm)}>Confirm permanent deletion</button>
      <button disabled={action.busy} onClick={() => setConfirm("")}>Keep content</button>
    </div>}
    <ErrorNotice error={action.error} />
  </details>;
}

export function WorkspaceLifecycle({ workspace }: { workspace: Workspace }) {
  const base = `/workspaces/${workspace.id}`;
  const batch = useResource<Batch | null>(`${base}/reindex`);
  const quotas = useResource<Quotas>(`${base}/quotas`);
  const action = useAction();
  const [profile, setProfile] = useState("E5");
  useEffect(() => {
    if (batch.data?.state !== "BUILDING") return;
    const timer = setTimeout(batch.reload, 3000);
    return () => clearTimeout(timer);
  }, [batch.data, batch.reload]);
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries([...form].map(([key, value]) => [key, Number(value)]));
    void action.run(async () => { await api(`${base}/quotas`, "PUT", values); quotas.reload(); });
  }
  return <details className="source-warnings">
    <summary>Workspace indexing and limits</summary>
    <p>Build a new index for every searchable document. The current indexes stay available until the entire build is ready. Previous indexes remain retained for citations.</p>
    <ErrorNotice error={batch.error} retry={batch.reload} />
    {batch.data && <p role="status">Latest reindex: {batch.data.state.toLowerCase()}</p>}
    <label htmlFor="index-profile">Search profile</label>
    <select id="index-profile" value={profile} disabled={action.busy || batch.data?.state === "BUILDING"} onChange={(event) => setProfile(event.target.value)}>
      <option value="E5">Semantic and keyword (local E5)</option><option value="NONE">Keyword only</option>
    </select>
    <p className="field-note">Semantic indexing needs the prepared local E5 model on the ingestion worker.</p>
    <button disabled={action.busy || batch.data === undefined || batch.data?.state === "BUILDING"} onClick={() => void action.run(async () => {
      await api(`${base}/reindex`, "POST", { profile }); batch.reload();
    })}>Build workspace index</button>
    {batch.data?.state === "BUILDING" && <button disabled={action.busy} onClick={() => void action.run(async () => {
      await api(`${base}/reindex`, "DELETE"); batch.reload();
    })}>Cancel workspace reindex</button>}
    <ErrorNotice error={quotas.error} retry={quotas.reload} />
    {quotas.data && <form key={JSON.stringify(quotas.data)} className="upload-form" aria-label="Workspace limits" onSubmit={save}>
      <h3>Workspace limits</h3>
      <p>Daily limits reset at midnight UTC. Lower limits affect new work; retained versions count toward source storage.</p>
      {([
        ["daily_answers", "Questions per day", 100], ["daily_embedding_tokens", "Embedding tokens per day", 500000],
        ["document_limit", "Documents", 500], ["storage_bytes", "Source storage bytes", 2147483648],
      ] as const).map(([key, label, max]) => <label key={key}>{label}<input name={key} type="number" min={0} max={max} step={1} required defaultValue={quotas.data![key]} disabled={action.busy} /></label>)}
      <button disabled={action.busy}>Save limits</button>
    </form>}
    <ErrorNotice error={action.error} />
  </details>;
}
