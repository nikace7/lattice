import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api, type DocumentSource, type SourceBlock, type Workspace } from "@/lib/api";
import { Documents } from "./documents";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const workspace: Workspace = { id: "workspace", name: "Library", role: "OWNER", revision: 1, accessEpoch: 1 };

function openSource(kind: string, locator: SourceBlock["locator"], text: string, overrides: Partial<DocumentSource> = {}) {
  const document: DocumentSource = {
    id: "document", title: "Policy", collectionId: "collection", sourceId: "source", revision: 1,
    kind, byteSize: 10, sha256: "hash", state: "EXTRACTED", error: "", retryable: false,
    pageCount: 0, warnings: [], canWrite: true, createdAt: "2026-10-02T00:00:00Z",
    ocrLanguage: "eng", pageReports: [], excludedPages: [], reviewReason: "",
    ...overrides,
  };
  vi.mocked(api).mockImplementation(async (path) => path === "/documents/document" ? document : {
    results: [{ id: "block", position: 0, text, originalText: text, locator, spanMap: [[0, text.length, 0, text.length]] }],
    next: null, previous: null,
  });
  return render(<Documents workspace={workspace} documentId="document" />);
}

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
