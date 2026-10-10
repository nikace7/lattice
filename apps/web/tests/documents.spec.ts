import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test("upload PDF and Nepali text, inspect exact locations and deny signed-out downloads", async ({ page, browser }) => {
  test.setTimeout(90_000);
  const suffix = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Username", { exact: true }).fill(`sources-${suffix}`);
  await page.getByLabel("Email address", { exact: true }).fill(`sources-${suffix}@example.test`);
  await page.getByLabel("Password", { exact: true }).fill("reading-room-739!");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.getByLabel("Workspace name").fill("Evidence library");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.getByRole("button", { name: "New collection", exact: true }).click();
  await page.getByLabel("Collection title", { exact: true }).fill("Source material");
  await page.getByRole("button", { name: "Create collection", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Source material", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await page.getByRole("button", { name: "Add document", exact: true }).first().click();
  await page.getByLabel("Document file").setInputFiles({
    name: "Nepali notes.txt", mimeType: "text/plain", buffer: Buffer.from("First line\r\nनेपाली e\u0301\nplain <script>alert(1)</script>"),
  });
  await page.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByRole("heading", { name: "Nepali notes.txt" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".source-status")).toContainText("Text extracted", { timeout: 30_000 });
  await page.getByRole("button", { name: /Line 2.*नेपाली/ }).click();
  await expect(page.getByRole("button", { name: /Line 2.*नेपाली/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("plain <script>alert(1)</script>", { exact: true })).toBeVisible();
  const originalUrl = await page.getByRole("link", { name: "Download original" }).getAttribute("href");
  const anonymous = await browser.newContext({ baseURL: "http://127.0.0.1:4411" });
  try {
    expect((await anonymous.request.get(originalUrl!)).status()).toBe(401);
  } finally { await anonymous.close(); }
  await page.getByRole("link", { name: "All documents" }).click();
  await page.getByRole("button", { name: "Add document", exact: true }).first().click();
  await page.getByLabel("Document file").setInputFiles({
    name: "Leave policy.pdf", mimeType: "application/pdf", buffer: readFileSync(resolve("../../fixtures/corpus/r2-policy.pdf")),
  });
  await page.getByRole("button", { name: "Upload document" }).click();
  await expect(page.locator(".source-status")).toContainText("Text extracted", { timeout: 30_000 });
  await page.getByRole("button", { name: /Page 1.*Submit requests/ }).click();
  await expect(page.locator(".source-highlight")).toBeVisible();
  expect(await page.locator(".pdf-page img").evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  for (const width of [1440, 768, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    if (width < 1100) {
      await page.getByRole("button", { name: "Source page", exact: true }).click();
      await expect(page.locator(".source-highlight")).toBeVisible();
      await page.getByRole("button", { name: "Back to extracted text" }).click();
      await expect(page.getByRole("button", { name: /Page 1.*Submit requests/ })).toBeFocused();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`source-${width}.png`), fullPage: true });
  }
  const download = await page.getByRole("link", { name: "Download original" }).getAttribute("href");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
  expect((await page.request.get(download!)).status()).toBe(401);
});
