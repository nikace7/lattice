import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError, type SourceQuote, type Turn, type Workspace } from "@/lib/api";
import { Ask, CitationReader, TurnCard } from "./ask";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.unstubAllGlobals(); });
const workspace: Workspace = { id: "workspace", name: "Library", role: "OWNER", revision: 1, accessEpoch: 1 };
const citation = { evidenceId: "S1", chunkId: "chunk", documentId: "doc", sourceId: "source", indexId: "index", title: "Leave policy", partial: true, quote: "five days", chunkStart: 0, chunkEnd: 9, spans: [{ blockId: "block", start: 0, end: 9, location: { line: 1 } }] };
const completed: Turn = { id: "turn", conversationId: "conversation", question: "How early?", state: "COMPLETED", sequence: 6, createdAt: "2026-10-06T00:00:00Z", error: "", unavailable: false, collectionIds: ["collection"], answer: { status: "ANSWERED", repaired: false, omittedPassages: 0, blocks: [{ text: "Request leave five days ahead.", citations: [citation] }] } };

test("question retry preserves the intent and draft, and Nepali composition does not submit", async () => {
  const submissions: Record<string, unknown>[] = [];
  vi.mocked(api).mockImplementation(async (path, method, body) => {
    if (method === "POST") {
      submissions.push(body as Record<string, unknown>);
      if (submissions.length === 1) throw new ApiError(503, "Connection interrupted");
      return completed;
    }
    if (path.endsWith("answer-capabilities")) return { enabled: true, message: "Fresh sources" };
    if (path.endsWith("document-status")) return { total: 0, ready: 0, processing: 0 };
    return { results: [], next: null, previous: null };
  });
  render(<Ask workspace={workspace} />);
  const question = screen.getByLabelText("Your question");
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask question" })).toBeEnabled());
  fireEvent.change(question, { target: { value: "बिदा कहिले माग्ने?" } });
  fireEvent.compositionStart(question);
  fireEvent.keyDown(question, { key: "Enter", keyCode: 229, isComposing: true });
  fireEvent.submit(screen.getByRole("form", { name: "Ask your sources" }));
  expect(submissions).toHaveLength(0);
  fireEvent.compositionEnd(question);
  fireEvent.submit(screen.getByRole("form", { name: "Ask your sources" }));
  await screen.findByText("Connection interrupted");
  expect(question).toHaveValue("बिदा कहिले माग्ने?");
  fireEvent.submit(screen.getByRole("form", { name: "Ask your sources" }));
  await waitFor(() => expect(push).toHaveBeenCalled());
  expect(submissions[1]).toEqual(submissions[0]);
});

test("retrieval-only mode disables generation without hiding conversation access", async () => {
  vi.mocked(api).mockImplementation(async (path) => path.endsWith("answer-capabilities") ? { enabled: false, message: "Generation unavailable" } : path.endsWith("document-status") ? { total: 0, ready: 0, processing: 0 } : { results: [], next: null, previous: null });
  render(<Ask workspace={{ ...workspace, role: "VIEWER" }} />);
  await screen.findByText("Generation unavailable");
  expect(screen.getByRole("button", { name: "Ask question" })).toBeDisabled();
  expect(screen.getByRole("region", { name: "Your private conversations" })).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Choose a collection" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Add documents" })).not.toBeInTheDocument();
});

test("SSE attaches with GETs and only displays a validated completed answer", async () => {
  const listeners = new Map<string, () => void>();
  const close = vi.fn();
  vi.stubGlobal("EventSource", class { onerror = null; close = close; addEventListener(name: string, callback: () => void) { listeners.set(name, callback); } });
  const pending = { ...completed, state: "GENERATING", sequence: 3, answer: null };
  vi.mocked(api).mockResolvedValue(pending);
  const settled = vi.fn();
  render(<TurnCard initial={pending} workspace={workspace} enabled={false} onSettled={settled} />);
  await screen.findByText("Preparing an answer");
  expect(screen.queryByText("Request leave five days ahead.")).not.toBeInTheDocument();
  vi.mocked(api).mockResolvedValue(completed);
  listeners.get("progress")?.();
  await screen.findByText("Request leave five days ahead.");
  expect(settled).toHaveBeenCalledTimes(1);
  expect(close).toHaveBeenCalled();
  expect(vi.mocked(api).mock.calls.every((call) => call[1] === "GET")).toBe(true);
});

test("source denial removes the whole displayed answer", async () => {
  vi.mocked(api).mockRejectedValue(new ApiError(404, "Source unavailable"));
  render(<TurnCard initial={completed} workspace={workspace} enabled={false} onSettled={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Inspect source 1.1: Leave policy" }));
  await screen.findByText("This answer uses sources that are no longer available.");
  expect(screen.queryByText("Request leave five days ahead.")).not.toBeInTheDocument();
});

test("citation text uses Unicode code-point offsets and keeps source HTML inert", async () => {
  const source: SourceQuote = { ...citation, sourceNumber: 1, olderVersion: false, kind: "TXT", quote: "cafe\u0301", spans: [{ blockId: "block", text: "😀 cafe\u0301 नेपाली <script>no</script>", start: 2, end: 7, location: { line: 2 } }] };
  vi.mocked(api).mockResolvedValue(source);
  const close = vi.fn();
  const { container } = render(<CitationReader turnId="turn" block={0} index={0} close={close} unavailable={vi.fn()} />);
  await screen.findByText("Line 2");
  expect(container.querySelector("mark")?.textContent).toBe("cafe\u0301");
  expect(container.querySelector("script")).toBeNull();
  fireEvent.keyDown(screen.getByRole("complementary", { name: "Cited source" }), { key: "Escape" });
  expect(close).toHaveBeenCalled();
});

test("older-version citation is labelled and closing restores its invoking button", async () => {
  vi.mocked(api).mockResolvedValue({ ...citation, sourceNumber: 1, olderVersion: true, kind: "TXT", spans: [{ blockId: "block", text: "five days", start: 0, end: 9, location: { line: 1 } }] });
  render(<TurnCard initial={completed} workspace={workspace} enabled={false} onSettled={vi.fn()} />);
  const button = screen.getByRole("button", { name: "Inspect source 1.1: Leave policy" });
  fireEvent.click(button);
  await screen.findByText("Older version");
  fireEvent.click(screen.getByRole("button", { name: "Back to answer" }));
  await waitFor(() => expect(button).toHaveFocus());
});

test("feedback waits for confirmation, persists selection and hides an answer after access denial", async () => {
  vi.mocked(api).mockResolvedValue({ ...completed, helpful: true });
  render(<TurnCard initial={completed} workspace={workspace} enabled={false} onSettled={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Helpful" })).toHaveAttribute("aria-pressed", "true"));
  expect(api).toHaveBeenCalledWith("/turns/turn/feedback", "POST", { helpful: true });
  vi.mocked(api).mockRejectedValue(new ApiError(404, "Answer unavailable"));
  fireEvent.click(screen.getByRole("button", { name: "Needs review" }));
  await screen.findByText("This answer uses sources that are no longer available.");
  expect(screen.queryByText("Request leave five days ahead.")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Helpful" })).not.toBeInTheDocument();
});

test("export authorization denial clears cached answers without downloading", async () => {
  let denied = false;
  const createObjectURL = vi.fn();
  vi.stubGlobal("URL", class extends URL { static createObjectURL = createObjectURL; });
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith("answer-capabilities")) return { enabled: true, message: "Fresh sources" };
    if (path.endsWith("document-status")) return { total: 1, ready: 1, processing: 0 };
    if (path.endsWith("/export")) { denied = true; throw new ApiError(404, "Conversation unavailable"); }
    if (path.endsWith("/turns")) {
      if (denied) throw new ApiError(404, "Conversation unavailable");
      return { results: [completed], next: null, previous: null };
    }
    return { results: [], next: null, previous: null };
  });
  render(<Ask workspace={workspace} conversationId="conversation" />);
  await screen.findByText("Request leave five days ahead.");
  fireEvent.click(screen.getByRole("button", { name: "Download conversation" }));
  await waitFor(() => expect(screen.queryByText("Request leave five days ahead.")).not.toBeInTheDocument());
  expect(await screen.findAllByText("Conversation unavailable")).not.toHaveLength(0);
  expect(createObjectURL).not.toHaveBeenCalled();
});
