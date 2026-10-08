import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError, type Evaluation, type Workspace } from "@/lib/api";
import { Evaluations } from "./evaluations";

vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), api: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const workspace: Workspace = { id: "workspace", name: "Library", role: "OWNER", revision: 1, accessEpoch: 1 };
const report: Evaluation = { id: "recorded", suite: "dev-v1", suiteHash: "hash", profile: { model: "E5" }, backend: "offline cosine only", elapsedSeconds: 12.48, description: "Synthetic development only", rows: [{ mode: "SEMANTIC", language: "en", questions: 1, goldGroupsFound: 0, goldGroups: 1, evidenceRecallAt8: 0, anyHitQuestions: 0, fullEvidenceQuestions: 0, meanReciprocalRank: 0 }], cases: [{ id: "case", mode: "SEMANTIC", language: "en", query: "When?", fullEvidence: false, expected: [{ id: "gold", title: "Expected policy", text: "Five days" }], retrieved: [{ id: "wrong", title: "Other policy", text: "Other evidence" }] }] };

test("comparison shows denominators and missing measurements; failure opens exact recorded evidence", async () => {
  vi.mocked(api).mockResolvedValue(report);
  render(<Evaluations workspace={workspace} reportId="recorded" />);
  await screen.findByRole("table", { name: "Recorded retrieval comparison" });
  expect(screen.getByText("0 / 1 (0%)")).toBeInTheDocument();
  expect(screen.getByText(/Citation validity.*not measured/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Show only incomplete evidence"));
  fireEvent.click(screen.getByRole("button", { name: /When/ }));
  expect(screen.getByText("Five days")).toBeInTheDocument();
  expect(screen.getByText("Other evidence")).toBeInTheDocument();
  expect(screen.getByText(/No answer was generated/)).toBeInTheDocument();
});

test("members cannot fetch owner diagnostics", () => {
  render(<Evaluations workspace={{ ...workspace, role: "VIEWER" }} />);
  expect(screen.getByText(/Only workspace owners/)).toBeInTheDocument();
  expect(api).not.toHaveBeenCalled();
});

test("failed load has retry and retains no stale report", async () => {
  vi.mocked(api).mockRejectedValueOnce(new ApiError(503, "Artifact unavailable")).mockResolvedValueOnce([]);
  render(<Evaluations workspace={workspace} />);
  await screen.findByText("Artifact unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("No recorded evaluations yet.");
});
