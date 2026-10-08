import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const workspace = { id: "10000000-0000-4000-8000-000000000001", name: "Reading room", role: "OWNER", revision: 1, accessEpoch: 1 };
const conversationId = "10000000-0000-4000-8000-000000000002";
const cite = { evidenceId: "S1", title: "Retained policy", partial: false, sourceId: "source", sourceNumber: 1, olderVersion: true, kind: "TXT", spans: [{ blockId: "block", text: "😀 Ask five days ahead. <script>inert</script>", start: 6, end: 15, location: { line: 1 } }] };
const report = { id: "recorded", suite: "synthetic-dev", suiteHash: "recorded-hash", profile: { model: "Recorded E5" }, backend: "offline cosine only", elapsedSeconds: 12.48, description: "Recorded synthetic development data", rows: [{ mode: "SEMANTIC", language: "en", questions: 1, goldGroupsFound: 0, goldGroups: 1, evidenceRecallAt8: 0, anyHitQuestions: 0, fullEvidenceQuestions: 0, meanReciprocalRank: 0 }], cases: [{ id: "case", mode: "SEMANTIC", language: "en", query: "When to ask?", fullEvidence: false, expected: [{ id: "gold", title: "Expected policy", text: "Five days ahead" }], retrieved: [{ id: "wrong", title: "Wrong policy", text: "Different evidence" }] }] };

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    if (path.endsWith("/auth/session")) data = { csrfToken: "test", user: { id: "reader", username: "reader", email: "reader@example.test" } };
    else if (path.endsWith(`/workspaces/${workspace.id}`)) data = workspace;
    else if (path.endsWith("/answer-capabilities")) data = { enabled: true, message: "Local generation is available" };
    else if (path.endsWith("/document-status")) data = { total: 1, ready: 1, processing: 0 };
    else if (path.endsWith("/turns")) data = { results: [{ id: "turn", conversationId: "conversation", question: "How early?", state: "COMPLETED", sequence: 1, createdAt: "2026-10-08T00:00:00Z", unavailable: false, error: "", collectionIds: [], answer: { status: "ANSWERED", repaired: false, omittedPassages: 0, blocks: [{ text: "Request leave five days ahead.", citations: [cite] }] } }], next: null, previous: null };
    else if (path.includes("/citations/")) data = cite;
    else if (path.endsWith("/evaluations/recorded")) data = report;
    else if (path.endsWith("/evaluations")) data = [report];
    else data = { results: [], next: null, previous: null };
    return route.fulfill({ json: data });
  });
});

for (const width of [360, 768, 1200, 1440]) {
  test(`reader, drawer and evaluation remain accessible at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/w/${workspace.id}/c/${conversationId}`);
    const button = page.getByRole("button", { name: "Inspect source 1.1: Retained policy" });
    await button.click();
    await expect(page.getByText("Older version", { exact: true })).toBeVisible();
    await expect(page.locator("mark")).toHaveText("five days");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const answer = page.getByText("Request leave five days ahead.");
    if (width < 1100) await expect(answer).toBeHidden();
    else {
      await expect(answer).toBeVisible();
      await page.getByLabel("Source panel width").fill("400");
      expect(await page.evaluate(() => localStorage.getItem("lattice-source-width"))).toBe("400");
    }
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`reader-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "Back to answer" }).click();
    await expect(button).toBeFocused();
    if (width >= 1100) {
      await button.click();
      await expect(page.getByLabel("Source panel width")).toHaveValue("400");
      await page.getByRole("button", { name: "Back to answer" }).click();
    }
    if (width < 768) {
      const menu = page.getByRole("button", { name: "Workspace menu" });
      await menu.click();
      await expect(page.getByRole("dialog", { name: "Workspace menu" })).toBeVisible();
      expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
      await menu.click();
    }
    await page.getByRole("link", { name: "Evaluations", exact: true }).click();
    await page.getByRole("link", { name: "synthetic-dev", exact: true }).click();
    await page.getByLabel("Show only incomplete evidence").check();
    await page.getByRole("button", { name: /When to ask/ }).click();
    await expect(page.getByRole("region", { name: "Expected evidence" })).toContainText("Five days ahead");
    await expect(page.getByRole("region", { name: "Actual answer" })).toContainText("No answer was generated");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`evaluation-${width}.png`), fullPage: true });
  });
}
