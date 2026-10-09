"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ComponentProps } from "react";
import type { Workspace } from "@/lib/api";
import { Icon } from "./icon";

export function CommandMenu({ workspace }: { workspace: Workspace }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const destinations: { path: string; label: string; note: string; icon: ComponentProps<typeof Icon>["name"] }[] = [
    { path: "documents", label: "Documents", note: "Read and manage your sources", icon: "documents" },
    { path: "search", label: "Search", note: "Find passages in your library", icon: "search" },
    { path: "ask", label: "Ask", note: "Ask a question with source citations", icon: "ask" },
    { path: "collections", label: "Collections", note: "Organize documents and access", icon: "collections" },
    ...(workspace.role === "OWNER" ? [
      { path: "evaluations", label: "Evaluations", note: "Inspect recorded retrieval evidence", icon: "chart" as const },
      { path: "settings/members", label: "People & access", note: "Manage membership and permissions", icon: "people" as const },
    ] : []),
  ];
  function open() { setQuery(""); dialog.current?.showModal(); search.current?.focus(); }
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && !event.isComposing) {
        event.preventDefault();
        if (dialog.current?.open) dialog.current.close();
        else { setQuery(""); dialog.current?.showModal(); search.current?.focus(); }
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const matches = destinations.filter((item) => `${item.label} ${item.note}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <>
    <button ref={trigger} type="button" className="command-trigger" onClick={open} aria-label="Quick navigation" aria-haspopup="dialog"><Icon name="search" /><span>Quick navigation</span><kbd>Ctrl / ⌘ K</kbd></button>
    <dialog ref={dialog} className="command-dialog" aria-labelledby="command-title" onClose={() => trigger.current?.focus()}>
      <div className="section-heading"><h2 id="command-title">Go to…</h2><button type="button" className="text-button" onClick={() => dialog.current?.close()}>Close</button></div>
      <label htmlFor="command-query">Find a destination</label>
      <input ref={search} id="command-query" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Documents, search, people…" />
      <nav aria-label="Quick navigation">{matches.map((item) => <Link key={item.path} href={`/w/${workspace.id}/${item.path}`} onClick={() => dialog.current?.close()}><Icon name={item.icon} /><span><strong>{item.label}</strong><small>{item.note}</small></span><Icon name="arrow" /></Link>)}</nav>
      {!matches.length && <p role="status">No destinations match. Try another word.</p>}
      <p className="field-note">Tab to a destination, Enter to open, Esc to close.</p>
    </dialog>
  </>;
}
