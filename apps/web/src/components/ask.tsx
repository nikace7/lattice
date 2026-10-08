"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { api, ApiError, type AnswerCapability, type Conversation, type Collection, type Page, type SourceQuote, type Turn, type Workspace } from "@/lib/api";
import type { components } from "@/lib/api.generated";
import { ErrorNotice, Loading, Pagination, useAction, useResource } from "./resource";

const active = (state: string) => ["QUEUED", "RETRIEVING", "GENERATING", "VALIDATING"].includes(state);
const labels: Record<string, string> = { QUEUED: "Question accepted", RETRIEVING: "Finding sources", GENERATING: "Preparing an answer", VALIDATING: "Checking the evidence", COMPLETED: "Answer ready", FAILED: "Answer failed", CANCELLED: "Cancelled", ACCESS_CHANGED: "Source access changed" };

export function Ask({ workspace, conversationId }: { workspace: Workspace; conversationId?: string }) {
  const capability = useResource<AnswerCapability>(`/workspaces/${workspace.id}/answer-capabilities`);
  const status = useResource<components["schemas"]["DocumentStatusData"]>(`/workspaces/${workspace.id}/document-status`);
  const router = useRouter();
  return <section>
    <p className="eyebrow">ASK, THEN READ THE EVIDENCE</p>
    <div className="section-heading"><h1>Your questions</h1>{conversationId && <Link href={`/w/${workspace.id}/ask`}>New conversation</Link>}</div>
    <ErrorNotice error={capability.error} retry={capability.reload} />
    <p className="muted">{capability.data?.message ?? "Checking answer availability…"}</p>
    <ErrorNotice error={status.error} retry={status.reload} />
    {status.data && <div className="source-status" aria-label="Document availability">
      <p>{status.data.ready} searchable · {status.data.processing} processing · {status.data.total} accessible documents</p>
      {status.data.total === 0 && <Link href={`/w/${workspace.id}/${["OWNER", "CURATOR"].includes(workspace.role) ? "documents" : "collections"}`}>{["OWNER", "CURATOR"].includes(workspace.role) ? "Add documents" : "Choose a collection"}</Link>}
    </div>}
    {conversationId ? <ConversationThread key={conversationId} workspace={workspace} id={conversationId} enabled={capability.data?.enabled ?? false} /> : <>
      <Composer workspace={workspace} enabled={capability.data?.enabled ?? false} onAccepted={(turn) => router.push(`/w/${workspace.id}/c/${turn.conversationId}`)} />
      <RecentConversations workspace={workspace} />
    </>}
  </section>;
}

function RecentConversations({ workspace }: { workspace: Workspace }) {
  const [path, setPath] = useState(`/workspaces/${workspace.id}/conversations`);
  const history = useResource<Page<Conversation>>(path);
  return <section aria-label="Your private conversations">
    <h2>Recent conversations</h2><p className="field-note">Only you can read these conversations.</p>
    <ErrorNotice error={history.error} retry={history.reload} />
    {!history.data && !history.error && <Loading>Loading your conversations…</Loading>}
    {history.data && <>{!history.data.results.length && <p>No conversations yet. Ask a question when local generation is available.</p>}
      <ul className="conversation-list">{history.data.results.map((conversation) => <li key={conversation.id}><Link href={`/w/${workspace.id}/c/${conversation.id}`}>{conversation.title}</Link></li>)}</ul>
      <Pagination page={history.data} onPage={setPath} />
    </>}
  </section>;
}

function Composer({ workspace, conversationId, enabled, onAccepted }: { workspace: Workspace; conversationId?: string; enabled: boolean; onAccepted: (turn: Turn) => void }) {
  const [path, setPath] = useState(`/workspaces/${workspace.id}/collections?pageSize=100`);
  const collections = useResource<Page<Collection>>(path);
  const [question, setQuestion] = useState("");
  const [submittedId, setSubmittedId] = useState<string>();
  const action = useAction();
  const identity = useRef<{ fingerprint: string; key: string; conversationId: string } | null>(null);
  const composing = useRef(false);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!enabled || composing.current) return;
    const values = new FormData(event.currentTarget);
    const collection = String(values.get("collection") ?? "");
    const fingerprint = JSON.stringify([question, collection]);
    if (identity.current?.fingerprint !== fingerprint) identity.current = { fingerprint, key: crypto.randomUUID(), conversationId: conversationId ?? identity.current?.conversationId ?? crypto.randomUUID() };
    const intent = identity.current;
    setSubmittedId(intent.conversationId);
    void action.run(async () => {
      const turn = await api<Turn>(`/workspaces/${workspace.id}/questions`, "POST", { conversationId: intent.conversationId, idempotencyKey: intent.key, question, ...(collection ? { collectionIds: [collection] } : {}) });
      identity.current = null;
      setQuestion("");
      onAccepted(turn);
    });
  }
  return <form className="question-composer" aria-label="Ask your sources" onSubmit={submit}>
    <fieldset disabled={!enabled || action.busy}>
      <legend>Question and source scope</legend>
      <label htmlFor="question-scope">Collection</label>
      <select id="question-scope" name="collection" key={path}><option value="">All accessible collections</option>{collections.data?.results.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}</select>
      {collections.data && <Pagination page={collections.data} onPage={setPath} />}
      <label htmlFor="question">Your question</label>
      <textarea id="question" required maxLength={4000} value={question} onChange={(e) => setQuestion(e.target.value)} onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && !composing.current && e.keyCode !== 229) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); }
      }} aria-describedby="question-help" />
      <p id="question-help" className="field-note">Enter to ask; Shift+Enter for a new line. Each question searches the selected sources afresh.</p>
      <button className="primary-button" disabled={!collections.data}>{action.busy ? "Submitting…" : "Ask question"}</button>
    </fieldset>
    <ErrorNotice error={collections.error} retry={collections.reload} />
    <ErrorNotice error={action.error} />
    {action.error && submittedId && <Link href={`/w/${workspace.id}/c/${submittedId}`}>Check whether the question was accepted</Link>}
  </form>;
}

function ConversationThread({ workspace, id, enabled }: { workspace: Workspace; id: string; enabled: boolean }) {
  const [path, setPath] = useState(`/conversations/${id}/turns`);
  const turns = useResource<Page<Turn>>(path);
  const running = turns.data?.results.some((turn) => active(turn.state)) ?? true;
  // The API enforces the active-turn constraint even while viewing an older history page.
  return <>
    <ErrorNotice error={turns.error} retry={turns.reload} />
    {!turns.data && !turns.error && <Loading>Loading the conversation…</Loading>}
    {turns.data && <>
      <div className="conversation-turns">{[...turns.data.results].reverse().map((turn) => <TurnCard key={turn.id} initial={turn} workspace={workspace} enabled={enabled && !running} onSettled={turns.reload} />)}</div>
      <Pagination page={turns.data} onPage={setPath} />
    </>}
    <Composer workspace={workspace} conversationId={id} enabled={enabled && !running && !turns.error} onAccepted={() => { setPath(`/conversations/${id}/turns`); turns.reload(); }} />
  </>;
}

export function TurnCard({ initial, workspace, enabled, onSettled }: { initial: Turn; workspace: Workspace; enabled: boolean; onSettled: () => void }) {
  const [turn, setTurn] = useState(initial);
  const [error, setError] = useState<Error>();
  const [citation, setCitation] = useState<{ block: number; index: number }>();
  const trigger = useRef<HTMLButtonElement | null>(null);
  const regenerateKey = useRef<string | null>(null);
  const action = useAction();
  const [sourceWidth, setSourceWidth] = useState(360);
  useEffect(() => {
    if (!active(initial.state)) return;
    const controller = new AbortController();
    const stream = new EventSource(`/api/v1/turns/${initial.id}/events`);
    let serial = 0, settled = false;
    async function refresh() {
      const current = ++serial;
      try {
        const next = await api<Turn>(`/turns/${initial.id}`, "GET", undefined, controller.signal);
        if (controller.signal.aborted || current !== serial) return;
        setTurn(next); setError(undefined);
        if (!active(next.state) && !settled) { settled = true; stream.close(); clearInterval(timer); onSettled(); }
      } catch (cause) {
        if (!controller.signal.aborted && current === serial) {
          setError(cause as Error); setCitation(undefined);
          if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) {
            stream.close(); clearInterval(timer);
            setTurn((old) => ({ ...old, answer: null, unavailable: true, state: "ACCESS_CHANGED" }));
          }
        }
      }
    }
    stream.addEventListener("progress", () => void refresh());
    stream.addEventListener("settled", () => void refresh());
    stream.addEventListener("access_changed", () => { ++serial; stream.close(); clearInterval(timer); setCitation(undefined); setTurn((old) => ({ ...old, answer: null, unavailable: true, state: "ACCESS_CHANGED" })); });
    stream.onerror = () => void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    void refresh();
    return () => { controller.abort(); stream.close(); clearInterval(timer); };
  }, [initial.id, initial.state, onSettled]);
  function closeSource() { setCitation(undefined); requestAnimationFrame(() => trigger.current?.focus()); }
  return <article className={`answer-turn ${citation ? "has-citation" : ""}`} style={{ "--source-width": `${sourceWidth}px` } as CSSProperties} aria-label="Question and answer">
    {citation && <label className="reader-size">Source panel width
      <input type="range" min={320} max={480} step={20} value={sourceWidth} onChange={(event) => {
        const width = Number(event.target.value); setSourceWidth(width);
        try { localStorage.setItem("lattice-source-width", String(width)); } catch { /* Optional preference. */ }
      }} />
    </label>}
    <div className="answer-body">
      <h2>{turn.question}</h2>
      <p role="status" aria-live="polite">{labels[turn.state] ?? turn.state}</p>
      <ErrorNotice error={error} />
      <ErrorNotice error={action.error} />
      {turn.error && <p className="error-notice" role="alert">{turn.error}</p>}
      {turn.unavailable && <p role="status">This answer uses sources that are no longer available.</p>}
      {!turn.unavailable && !error && turn.answer && <>
        {turn.answer.status === "INSUFFICIENT_EVIDENCE" && <p>There is not enough verified evidence to answer. Try a more specific question or choose another collection.</p>}
        {turn.answer.status === "CONFLICTING_EVIDENCE" && <p className="source-warnings">The sources disagree. Review each cited position.</p>}
        {turn.answer.omittedPassages > 0 && <p className="field-note">Some retrieved passages were omitted to keep the evidence within the answer limit.</p>}
        {turn.answer.blocks.map((block, b) => <div className="answer-block" key={b}>
          <p>{block.text}</p>
          <div className="citation-buttons">{block.citations.map((cite, c) => <button key={c} onClick={(event) => {
            trigger.current = event.currentTarget;
            try {
              const saved = Number(localStorage.getItem("lattice-source-width"));
              if (saved >= 320 && saved <= 480) setSourceWidth(saved);
            } catch { /* Reader remains usable without preference storage. */ }
            setCitation({ block: b, index: c });
          }} aria-label={`Inspect source ${b + 1}.${c + 1}: ${cite.title}`} aria-expanded={citation?.block === b && citation?.index === c}>[{b + 1}.{c + 1}] {cite.title}{cite.partial ? " · Partial source" : ""}</button>)}</div>
        </div>)}
        {!!turn.answer.blocks.length && <p className="field-note">Quoted passages were checked. Model grounding can still be wrong; review the original evidence.</p>}
      </>}
      {active(turn.state) && <button disabled={action.busy} onClick={() => void action.run(async () => { const next = await api<Turn>(`/turns/${turn.id}/cancel`, "POST"); setTurn(next); onSettled(); })}>Stop answer</button>}
      {!active(turn.state) && enabled && <button disabled={action.busy} onClick={() => void action.run(async () => {
        regenerateKey.current ??= crypto.randomUUID();
        await api(`/workspaces/${workspace.id}/questions`, "POST", { conversationId: turn.conversationId, idempotencyKey: regenerateKey.current, question: turn.question, collectionIds: turn.collectionIds, replacesTurnId: turn.id });
        regenerateKey.current = null;
        onSettled();
      })}>Ask again with current sources</button>}
    </div>
    {citation && !turn.unavailable && !error && <CitationReader key={`${citation.block}:${citation.index}`} turnId={turn.id} block={citation.block} index={citation.index} close={closeSource} unavailable={() => { setCitation(undefined); setTurn((old) => ({ ...old, answer: null, unavailable: true })); }} />}
  </article>;
}

export function CitationReader({ turnId, block, index, close, unavailable }: { turnId: string; block: number; index: number; close: () => void; unavailable: () => void }) {
  const source = useResource<SourceQuote>(`/turns/${turnId}/citations/${block}/${index}`);
  const heading = useRef<HTMLHeadingElement | null>(null);
  const [selected, setSelected] = useState(0);
  useEffect(() => { heading.current?.focus(); }, []);
  useEffect(() => { if (source.error instanceof ApiError && [401, 403, 404].includes(source.error.status)) unavailable(); }, [source.error, unavailable]);
  const span = source.data?.spans[selected];
  const location = span?.location as { page?: number; bbox?: number[]; line?: number; paragraph?: number; headingPath?: string[]; table?: number; row?: number; cell?: number } | undefined;
  const box = location?.bbox;
  return <aside className="citation-reader" aria-label="Cited source" onKeyDown={(event) => { if (event.key === "Escape") close(); }}>
    <button onClick={close}>Back to answer</button><h3 ref={heading} tabIndex={-1}>Cited source</h3>
    <ErrorNotice error={source.error} retry={source.reload} />
    {!source.data && !source.error && <Loading>Checking source access…</Loading>}
    {source.data && <>
      <h2>{source.data.title}</h2><p className="field-note">Source version {source.data.sourceNumber} · {source.data.sourceId}</p>
      {source.data.olderVersion && <span className="access-badge">Older version</span>}
      {source.data.partial && <p className="source-warnings">Partial document indexed</p>}
      <p>Highlighted text is the exact cited passage.</p>
      {source.data.spans.map((item, i) => {
        const characters = Array.from(item.text);
        return <div className="citation-context" key={`${item.blockId}:${i}`}>
          <p>{characters.slice(0, item.start).join("")}<mark>{characters.slice(item.start, item.end).join("")}</mark>{characters.slice(item.end).join("")}</p>
          <button onClick={() => setSelected(i)} aria-pressed={selected === i}>Inspect location {i + 1}</button>
        </div>;
      })}
      <p>{location?.page ? `Physical page ${location.page}` : location?.table ? `Table ${location.table}, row ${location.row}, cell ${location.cell}` : location?.paragraph ? `Paragraph ${location.paragraph}` : `Line ${location?.line ?? "—"}`}{location?.headingPath?.length ? ` · ${location.headingPath.join(" › ")}` : ""}</p>
      {source.data.kind === "PDF" && location?.page && <>
        <p className="field-note">The page outline marks the containing source block; the text above marks the exact quote.</p>
        <div className="pdf-page">
          {/* Same-origin permission-checked image; bypass shared image optimization caches. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/api/v1/sources/${source.data.sourceId}/pages/${location.page}`} alt={`Source page ${location.page} of ${source.data.title}. Exact quoted text is available above.`} />
          {box && <div className="source-highlight" role="img" aria-label="Containing source block" style={{ left: `${box[0] * 100}%`, top: `${box[1] * 100}%`, width: `${(box[2] - box[0]) * 100}%`, height: `${(box[3] - box[1]) * 100}%` }} />}
        </div>
      </>}
      <a href={`/api/v1/sources/${source.data.sourceId}/original`} download>Download original source version</a>
    </>}
  </aside>;
}
