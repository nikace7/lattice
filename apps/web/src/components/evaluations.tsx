"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import type { Evaluation, Workspace } from "@/lib/api";
import { ErrorNotice, Loading, useResource } from "./resource";

export function Evaluations({ workspace, reportId }: { workspace: Workspace; reportId?: string }) {
  if (workspace.role !== "OWNER") return <p role="status">Only workspace owners can view evaluation diagnostics.</p>;
  return <EvaluationReports key={reportId ?? "list"} workspace={workspace} reportId={reportId} />;
}

function EvaluationReports({ workspace, reportId }: { workspace: Workspace; reportId?: string }) {
  const report = useResource<Evaluation | Evaluation[]>(`/workspaces/${workspace.id}/evaluations${reportId ? `/${reportId}` : ""}`);
  const [failuresOnly, setFailuresOnly] = useState(false);
  const [selected, setSelected] = useState<string>();
  const heading = useRef<HTMLHeadingElement>(null);
  const reports = report.data ? Array.isArray(report.data) ? report.data : [report.data] : [];
  const detail = reportId ? reports[0] : undefined;
  const cases = detail?.cases.filter((item) => !failuresOnly || item.fullEvidence === false) ?? [];
  const selectedCase = cases.find((item) => item.id === selected);
  return <section aria-labelledby="evaluation-title">
    <p className="eyebrow">Workspace / Recorded evaluations</p>
    <div className="section-heading"><h1 id="evaluation-title">Evaluations</h1>{reportId && <Link href={`/w/${workspace.id}/evaluations`}>All recorded evaluations</Link>}</div>
    <p>These are recorded synthetic retrieval runs shared across owner diagnostics. They do not evaluate this workspace’s documents or prove answer quality.</p>
    <ErrorNotice error={report.error} retry={report.reload} />
    {!report.data && !report.error && <Loading>Loading recorded evaluations…</Loading>}
    {report.data && !reports.length && <p>No recorded evaluations yet.</p>}
    {reports.map((item) => <section key={item.id} className="evaluation-report" aria-label={item.suite}>
      <h2>{reportId ? item.suite : <Link href={`/w/${workspace.id}/evaluations/${item.id}`}>{item.suite}</Link>}</h2>
      <p>{item.description}</p>
      <p className="field-note">Backend: {item.backend} · Total run duration: {item.elapsedSeconds}s. This includes setup and is not per-question latency.</p>
      <details><summary>Corpus and model versions</summary><p className="field-note">Suite/corpus hash: {item.suiteHash}</p><pre>{JSON.stringify(item.profile, null, 2)}</pre></details>
      <div className="search-score-table" role="region" aria-label="Retrieval comparison" tabIndex={0}>
        <table aria-label="Recorded retrieval comparison"><caption>Retrieval results by mode and language</caption><thead><tr><th scope="col">Mode / language</th><th scope="col">Evidence Recall@8</th><th scope="col">Any evidence</th><th scope="col">Full evidence</th><th scope="col">MRR</th></tr></thead>
          <tbody>{item.rows.map((row) => <tr key={`${row.mode}:${row.language}`}><th scope="row">{row.mode} / {row.language}</th><td>{row.goldGroupsFound} / {row.goldGroups} ({Math.round(row.evidenceRecallAt8 * 100)}%)</td><td>{row.anyHitQuestions} / {row.questions}</td><td>{row.fullEvidenceQuestions} / {row.questions}</td><td>{row.meanReciprocalRank.toFixed(3)}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="field-note">Citation validity, human-supported claim rate, abstention, per-question latency and token usage: not measured in this retrieval run.</p>
      <details><summary>Metric definitions</summary><p>{item.metricDefinition}</p></details>
    </section>)}
    {detail && <section aria-label="Evaluation cases">
      <h2>Inspect cases</h2><label className="checkbox-label"><input type="checkbox" checked={failuresOnly} onChange={(event) => { setFailuresOnly(event.target.checked); setSelected(undefined); }} />Show only incomplete evidence</label>
      {!cases.length && <p>No incomplete evidence cases in this recorded run.</p>}
      <ul className="evaluation-cases">{cases.map((item) => <li key={item.id}><button aria-expanded={selected === item.id} aria-controls="evaluation-case-detail" onClick={() => { setSelected(item.id); requestAnimationFrame(() => heading.current?.focus()); }}>{item.query} <small>{item.mode} / {item.language} · {item.fullEvidence === null ? "Abstention not measured" : item.fullEvidence ? "Full evidence retrieved" : "Incomplete evidence"}</small></button></li>)}</ul>
      {selectedCase && <div id="evaluation-case-detail"><h2 ref={heading} tabIndex={-1}>{selectedCase.query}</h2><div className="evaluation-evidence">
        <section aria-label="Expected evidence"><h3>Expected evidence</h3>{!selectedCase.expected.length && <p>No permitted gold evidence is labelled for this question.</p>}{selectedCase.expected.map((doc) => <article key={doc.id}><h4>{doc.title}</h4><p lang={selectedCase.language}>{doc.text}</p></article>)}</section>
        <section aria-label="Retrieved evidence"><h3>Retrieved evidence, in rank order</h3>{selectedCase.retrieved.map((doc, i) => <article key={`${doc.id}:${i}`}><h4>{i + 1}. {doc.title}</h4><p lang={selectedCase.language}>{doc.text}</p></article>)}</section>
        <section aria-label="Actual answer"><h3>Actual answer</h3><p>No answer was generated in this retrieval-only evaluation.</p></section>
      </div></div>}
    </section>}
  </section>;
}
