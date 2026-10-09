import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const id = "10000000-0000-4000-8000-000000000001";
const workspace = { id, name: "Cedar Studio", role: "CURATOR", revision: 1, accessEpoch: 1 };
const documents = [
  { id: "leave", title: "Annual leave policy", kind: "PDF", state: "REVIEWED", currentSourceId: "v2", sourceNumber: 2, byteSize: 28000 },
  { id: "onboarding", title: "New starter handbook", kind: "DOCX", state: "EXTRACTED", currentSourceId: "v1", sourceNumber: 1, byteSize: 15200 },
  { id: "meeting", title: "Project kickoff notes", kind: "MD", state: "NEEDS_REVIEW", currentSourceId: null, sourceNumber: 1, byteSize: 2200 },
  { id: "research", title: "Research interview summary", kind: "TXT", state: "EXTRACTING", currentSourceId: null, sourceNumber: 1, byteSize: 3400 },
];

async function fixture(page: import("@playwright/test").Page, signedIn = true) {
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const data = path.endsWith("/auth/session") ? { csrfToken: "test", user: signedIn ? { id: "reader", username: "sam.curator", email: "sam@lattice.invalid" } : null } : path.endsWith(`/workspaces/${id}`) ? workspace : path.endsWith("/collections") ? { results: [{ id: "handbook", title: "Handbook", canWrite: true, access: "WORKSPACE" }], next: null, previous: null } : path.endsWith("/documents") ? { results: documents, next: null, previous: null } : { results: [], next: null, previous: null };
    return route.fulfill({ json: data });
  });
}

for (const width of [360, 768, 1440]) {
  test(`library filters, navigation and typography at ${width}px`, async ({ page }) => {
    await fixture(page);
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/w/${id}/documents`);
    await expect(page.getByText("Annual leave policy")).toBeVisible();
    await expect(page.getByRole("form", { name: "Upload a document" })).toBeHidden();
    await page.getByLabel("Document status").selectOption("REVIEW");
    await expect(page.getByText("Project kickoff notes")).toBeVisible();
    await expect(page.getByText("Annual leave policy")).toBeHidden();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await page.getByLabel("Find on this page").fill("leave");
    await expect(page.getByText("New starter handbook")).toBeHidden();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await page.getByRole("button", { name: "Add document", exact: true }).click();
    await expect(page.getByRole("form", { name: "Upload a document" })).toBeVisible();
    await page.getByRole("button", { name: "Close upload" }).click();
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: "Go to…" })).toBeVisible();
    await expect(page.getByLabel("Find a destination")).toBeFocused();
    await page.getByLabel("Find a destination").fill("search");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: /Search Find passages/ })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button", { name: /Quick navigation/ })).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.evaluate(() => { const note = document.createElement("p"); note.className = "field-note"; note.textContent = "Design preview · fictional documents · mocked API"; document.querySelector("main")?.prepend(note); });
    await page.screenshot({ path: test.info().outputPath(`library-${width}.png`), fullPage: true });
  });
  test(`sign-in and password visibility at ${width}px`, async ({ page }) => {
    await fixture(page, false);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await page.getByLabel("Password", { exact: true }).fill("fictional-password");
    await page.getByRole("button", { name: "Show password" }).click();
    await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
    await page.getByRole("button", { name: "Hide password" }).click();
    await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "password");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`sign-in-${width}.png`), fullPage: true });
  });
}
