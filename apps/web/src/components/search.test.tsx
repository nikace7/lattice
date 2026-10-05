import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api, type Workspace } from "@/lib/api";
import { Search } from "./search";

vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const workspace: Workspace = { id: "workspace", name: "Library", role: "OWNER", revision: 1, accessEpoch: 1 };
const response = { mode: "KEYWORD", runId: "run", diagnostics: { elapsedMs: 10, lexical: [], vector: [], selected: [], corpusHash: "hash", profileHash: "profile" }, results: [{ chunkId: "chunk", documentId: "doc", title: "Policy", text: "<script>untrusted</script> नेपाली", partial: true }] };

test("search sends scope, renders inert source passages and clears results on scope changes", async () => {
  vi.mocked(api).mockImplementation(async (path) => path.endsWith("/search") ? response : { results: [{ id: "collection", title: "Policies" }], next: null, previous: null });
  const { container } = render(<Search workspace={workspace} />);
  await screen.findByRole("option", { name: "Policies" });
  fireEvent.change(screen.getByLabelText("Search words or a question"), { target: { value: "leave" } });
  fireEvent.change(screen.getByLabelText("Collection"), { target: { value: "collection" } });
  fireEvent.click(screen.getByLabelText("Show retrieval details"));
  fireEvent.submit(screen.getByRole("form", { name: "Search sources" }));
  await screen.findByText(response.results[0].text);
  expect(api).toHaveBeenCalledWith("/workspaces/workspace/search", "POST", { query: "leave", mode: "KEYWORD", details: true, collectionIds: ["collection"] }, expect.any(AbortSignal));
  expect(container.querySelector("script")).toBeNull();
  expect(screen.getByRole("link", { name: /Inspect source passage/ })).toHaveAttribute("href", "/w/workspace/documents/doc/passages/chunk");
  expect(screen.getByText("Partial document indexed")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Collection"), { target: { value: "" } });
  expect(screen.queryByText(response.results[0].text)).not.toBeInTheDocument();
});

test("readers cannot request diagnostics and failed searches keep the query without stale results", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith("/search")) throw new Error("Scope changed. Search again.");
    return { results: [], next: null, previous: null };
  });
  render(<Search workspace={{ ...workspace, role: "VIEWER" }} />);
  expect(screen.queryByLabelText("Show retrieval details")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Search words or a question"), { target: { value: "leave" } });
  fireEvent.submit(screen.getByRole("form", { name: "Search sources" }));
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Search words or a question")).toHaveValue("leave");
  expect(screen.queryByRole("link", { name: /Inspect source/ })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Search" })).toBeEnabled());
});

test("late response from an aborted scope never replaces the current view", async () => {
  let resolve: (value: unknown) => void = () => {};
  vi.mocked(api).mockImplementation(async (path) => path.endsWith("/search") ? new Promise((done) => { resolve = done; }) : { results: [], next: null, previous: null });
  render(<Search workspace={workspace} />);
  fireEvent.change(screen.getByLabelText("Search words or a question"), { target: { value: "leave" } });
  fireEvent.submit(screen.getByRole("form", { name: "Search sources" }));
  fireEvent.change(screen.getByLabelText("Search method"), { target: { value: "HYBRID" } });
  resolve(response);
  await waitFor(() => expect(screen.getByRole("button", { name: "Search" })).toBeEnabled());
  expect(screen.queryByText(response.results[0].text)).not.toBeInTheDocument();
});
