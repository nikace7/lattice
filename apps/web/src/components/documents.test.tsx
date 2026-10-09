import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api, type DocumentSource, type SourceBlock, type Workspace } from "@/lib/api";
import { Documents } from "./documents";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const workspace: Workspace = { id: "workspace", name: "Library", role: "OWNER", revision: 1, accessEpoch: 1 };

test("document filters apply to the current page without presenting it as the entire library", async () => {
  vi.mocked(api).mockImplementation(async (path) => path.includes("collections") ? { results: [], next: null, previous: null } : {
    results: [
      { id: "a", title: "Leave policy", kind: "PDF", state: "REVIEWED", currentSourceId: "s", sourceNumber: 1, byteSize: 1200 },
      { id: "b", title: "Meeting notes", kind: "TXT", state: "FAILED", currentSourceId: null, sourceNumber: 1, byteSize: 500 },
    ], next: "/api/v1/workspaces/workspace/documents?page=2", previous: null,
  });
  render(<Documents workspace={{ ...workspace, role: "VIEWER" }} />);
  await screen.findByText("Leave policy");
  fireEvent.change(screen.getByLabelText("Find on this page"), { target: { value: "notes" } });
  expect(screen.queryByText("Leave policy")).not.toBeInTheDocument();
  expect(screen.getByText("Meeting notes")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Document status"), { target: { value: "READY" } });
  expect(screen.getByText("No documents match these filters on this page.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(screen.getByText("Leave policy")).toBeInTheDocument();
  expect(screen.getByText("2 of 2 documents on this page")).toBeInTheDocument();
});

test("collapsing and reopening an upload after an ambiguous failure preserves its submission identifier", async () => {
  const submissions: FormData[] = [];
  vi.mocked(api).mockImplementation(async (path, method, body) => {
    if (method === "POST") { submissions.push(body as FormData); throw new Error("Response lost"); }
    return { results: path.includes("collections") ? [{ id: "c", title: "Handbook", canWrite: true }] : [], next: null, previous: null };
  });
  render(<Documents workspace={{ ...workspace, role: "CURATOR" }} />);
  fireEvent.click((await screen.findAllByRole("button", { name: "Add document" }))[0]);
  fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [new File(["Policy"], "policy.txt")] } });
  fireEvent.submit(screen.getByRole("form", { name: "Upload a document" }));
  await screen.findByText("Response lost");
  fireEvent.click(screen.getByRole("button", { name: "Close upload" }));
  fireEvent.click(screen.getAllByRole("button", { name: "Add document" })[0]);
  fireEvent.submit(screen.getByRole("form", { name: "Upload a document" }));
  await waitFor(() => expect(submissions).toHaveLength(2));
  expect(submissions[1].get("uploadId")).toBe(submissions[0].get("uploadId"));
});

function openSource(kind: string, locator: SourceBlock["locator"], text: string, overrides: Partial<DocumentSource> = {}, chunkId?: string) {
  const document: DocumentSource = {
    id: "document", title: "Policy", collectionId: "collection", sourceId: "source", revision: 1,
    kind, byteSize: 10, sha256: "hash", state: "EXTRACTED", error: "", retryable: false,
    pageCount: 0, warnings: [], canWrite: true, createdAt: "2026-10-02T00:00:00Z",
    ocrLanguage: "eng", pageReports: [], excludedPages: [], reviewReason: "",
    index: null, sourceNumber: 1, currentSourceId: null,
    ...overrides,
  };
  vi.mocked(api).mockImplementation(async (path) => path === "/documents/document/versions" ? { results: [], next: null, previous: null } : path.startsWith("/documents/document") ? document : {
    results: [{ id: "block", position: 0, text, originalText: text, locator, spanMap: [[0, text.length, 0, text.length]] }],
    next: null, previous: null,
  });
  return render(<Documents workspace={workspace} documentId="document" chunkId={chunkId} />);
}

test("search passage opens only its source blocks and the matching physical PDF page", async () => {
  openSource("PDF", { page: 3, bbox: [0, 0, 1, 1] }, "Matched passage", { pageCount: 4 }, "chunk");
  await screen.findByRole("button", { name: /Page 3.*Matched passage/ });
  expect(api).toHaveBeenCalledWith("/sources/source/blocks?chunkId=chunk", "GET", undefined, expect.any(AbortSignal));
  expect(screen.getByRole("img", { name: /Original page 3/ })).toHaveAttribute("src", "/api/v1/sources/source/pages/3");
  expect(screen.getByRole("link", { name: "Open the full document" })).toHaveAttribute("href", "/w/workspace/documents/document");
});

test("deletion requires a separate confirmation and uses the displayed revision", async () => {
  openSource("TXT", { line: 1 }, "Retained text", { revision: 4 });
  fireEvent.click(await screen.findByRole("button", { name: "Delete document" }));
  expect(api).not.toHaveBeenCalledWith("/documents/document/delete", "POST", expect.anything());
  fireEvent.click(screen.getByRole("button", { name: "Confirm permanent deletion" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/documents/document/delete", "POST", { expectedRevision: 4 }));
});

test("replacement preserves its submission identifier after a network failure", async () => {
  openSource("TXT", { line: 1 }, "Old searchable text");
  fireEvent.click(await screen.findByRole("button", { name: "Replace source" }));
  fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [new File(["New text"], "new.txt")] } });
  const original = vi.mocked(api).getMockImplementation()!;
  const submissions: FormData[] = [];
  vi.mocked(api).mockImplementation(async (path, method, body, signal) => {
    if (path.endsWith("/replace")) { submissions.push(body as FormData); throw new Error("Connection lost"); }
    return original(path, method, body, signal);
  });
  fireEvent.submit(screen.getByRole("form", { name: "Replace document" }));
  await screen.findByText("Connection lost");
  fireEvent.submit(screen.getByRole("form", { name: "Replace document" }));
  await waitFor(() => expect(submissions).toHaveLength(2));
  expect(submissions[0].get("uploadId")).toBe(submissions[1].get("uploadId"));
  expect(submissions[0].get("expectedRevision")).toBe("1");
});

test("Word source selection shows paragraph and cell references without page numbers", async () => {
  openSource("DOCX", { paragraph: 4, table: 1, row: 2, cell: 3, headingPath: ["Policy"] }, "नेपाली");
  const passage = await screen.findByRole("button", { name: /Table 1, row 2, cell 3.*Paragraph 4/ });
  fireEvent.click(passage);
  expect(passage).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText(/Selected Table 1, row 2, cell 3/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Physical page")).not.toBeInTheDocument();
});

test("Markdown HTML and remote embeds remain inert source text", async () => {
  const text = '![remote](https://example.invalid/image) <script>alert(1)</script>';
  const { container } = openSource("MD", { line: 3, offset: 10 }, text);
  const passage = await screen.findByRole("button", { name: /Line 3/ });
  expect(passage).toHaveTextContent(text);
  expect(container.querySelectorAll("script, img, iframe")).toHaveLength(0);
  expect(container.querySelector('a[href^="https://example.invalid"]')).toBeNull();
});

test("index request carries the current revision and read-only users have no index actions", async () => {
  openSource("TXT", { line: 1 }, "Text");
  fireEvent.click(await screen.findByRole("button", { name: "Prepare search index" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/documents/document/index", "POST", { expectedRevision: 1 }));
  cleanup();
  openSource("TXT", { line: 1 }, "Text", { canWrite: false });
  await screen.findByText("Not indexed yet");
  expect(screen.queryByRole("button", { name: "Prepare search index" })).not.toBeInTheDocument();
});

test("running index can be cancelled and ready partial index is labelled", async () => {
  openSource("TXT", { line: 1 }, "Text", { index: { state: "EMBEDDING", active: false, chunkCount: 2, error: "", canRetry: false, semantic: true } });
  fireEvent.click(await screen.findByRole("button", { name: "Cancel indexing" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/documents/document/cancel-index", "POST", { expectedRevision: 1 }));
  cleanup();
  openSource("PDF", { page: 1 }, "Text", { excludedPages: [2], index: { state: "READY", active: true, chunkCount: 2, error: "", canRetry: false, semantic: true } });
  await screen.findByText(/Partial document indexed/);
  expect(screen.queryByRole("button", { name: "Cancel indexing" })).not.toBeInTheDocument();
});

test("review requires failed-page exclusion and submits a revision with the review note", async () => {
  openSource("PDF", { page: 1, bbox: [0, 0, 1, 1] }, "Recognized text", {
    state: "NEEDS_REVIEW", pageCount: 2, pageReports: [
      { page: 1, status: "OCR", preview: true, confidence: 90, language: "eng", engine: "tesseract test" },
      { page: 2, status: "FAILED", preview: false, confidence: null, language: "", engine: "" },
    ],
  });
  const failed = await screen.findByRole("checkbox", { name: /Exclude page 2/ });
  expect(failed).toBeChecked();
  expect(failed).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /Exclude page 1/ }));
  expect(screen.getByRole("button", { name: "Accept extraction" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: /Exclude page 1/ }));
  fireEvent.change(screen.getByLabelText("Review note"), { target: { value: "Compared with the source" } });
  fireEvent.submit(screen.getByRole("form", { name: "Review extraction" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/documents/document/accept-review", "POST", {
    expectedRevision: 1, excludedPages: [2], reason: "Compared with the source",
  }));
});

test("read-only users cannot accept extraction", async () => {
  openSource("PDF", { page: 1 }, "Text", {
    state: "NEEDS_REVIEW", canWrite: false, pageCount: 1,
    pageReports: [{ page: 1, status: "OCR", preview: true, confidence: 90, language: "eng", engine: "test" }],
  });
  await screen.findByText("Policy");
  expect(screen.queryByRole("form", { name: "Review extraction" })).not.toBeInTheDocument();
});

test("active extraction can be cancelled with its revision but cannot be retried early", async () => {
  openSource("TXT", {}, "", { state: "EXTRACTING", retryable: false });
  const cancel = await screen.findByRole("button", { name: "Cancel extraction" });
  expect(screen.queryByRole("button", { name: "Retry extraction" })).not.toBeInTheDocument();
  fireEvent.click(cancel);
  await waitFor(() => expect(api).toHaveBeenCalledWith("/documents/document/cancel", "POST", { expectedRevision: 1 }));
  expect(screen.queryByRole("button", { name: "Retry extraction" })).not.toBeInTheDocument();
});

test("cancelled extraction offers retry and keeps its original download", async () => {
  openSource("TXT", {}, "", { state: "CANCELLED", retryable: true });
  fireEvent.click(await screen.findByRole("button", { name: "Retry extraction" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("/documents/document/retry", "POST", { expectedRevision: 1 }));
  expect(await screen.findByRole("link", { name: "Download original" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Cancel extraction" })).not.toBeInTheDocument();
});
