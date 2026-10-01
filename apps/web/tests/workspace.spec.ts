import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("create an account and workspace, grant and revoke collection access, then sign out", async ({
  page,
  browser,
}) => {
  const suffix = Date.now().toString(36);
  const owner = `owner-${suffix}`,
    reader = `reader-${suffix}`;
  const password = "reading-room-739!";
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Username", { exact: true }).fill(owner);
  await page.getByLabel("Email address", { exact: true }).fill(`${owner}@example.test`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your workspaces" }),
  ).toBeVisible();
  await page.getByLabel("Workspace name").fill("Studio library");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Collections", exact: true }),
  ).toBeVisible();
  const workspacePath = new URL(page.url()).pathname;
  await page
    .getByRole("button", { name: "New collection", exact: true })
    .click();
  await page
    .getByLabel("Collection title", { exact: true })
    .fill("Private research");
  await page
    .getByLabel("Who can read it?", { exact: true })
    .selectOption("RESTRICTED");
  await page
    .getByRole("button", { name: "Create collection", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Private research", exact: true }),
  ).toBeVisible();
  const readerContext = await browser.newContext({
    baseURL: "http://127.0.0.1:4411",
  });
  try {
    const session = await readerContext.request.get("/api/v1/auth/session");
    const csrf = (await session.json()).csrfToken;
    const registration = await readerContext.request.post(
      "/api/v1/auth/register",
      {
        data: { username: reader, email: `${reader}@example.test`, password },
        headers: { "X-CSRFToken": csrf },
      },
    );
    expect(registration.status()).toBe(201);
    await page.getByRole("link", { name: "People & access" }).click();
    await page.getByLabel("Username", { exact: true }).fill(reader);
    await page.getByLabel("Role", { exact: true }).selectOption("VIEWER");
    await page.getByRole("button", { name: "Add person", exact: true }).click();
    await expect(
      page.getByRole("form", { name: `Membership for ${reader}` }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Collections", exact: true }).click();
    await page.getByRole("button", { name: /Private research/ }).click();
    await page.getByLabel(`${reader}viewer`).selectOption("read");
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().endsWith("/grants") &&
          response.request().method() === "PUT" &&
          response.status() === 200,
      ),
      page.getByRole("button", { name: "Save access" }).click(),
    ]);
    await expect(page.getByLabel(`${reader}viewer`)).toHaveValue("read");
    const readerPage = await readerContext.newPage();
    await readerPage.goto(workspacePath);
    await expect(
      readerPage.getByRole("button", { name: /Private research/ }),
    ).toBeVisible();
    await expect(
      readerPage.getByRole("button", { name: "New collection" }),
    ).toHaveCount(0);
    await page.getByLabel(`${reader}viewer`).selectOption("none");
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().endsWith("/grants") &&
          response.request().method() === "PUT" &&
          response.status() === 200,
      ),
      page.getByRole("button", { name: "Save access" }).click(),
    ]);
    await expect(page.getByLabel(`${reader}viewer`)).toHaveValue("none");
    await readerPage.reload();
    await expect(
      readerPage.getByRole("heading", {
        name: "There’s room for knowledge here.",
      }),
    ).toBeVisible();
    await expect(
      readerPage.getByRole("button", { name: /Private research/ }),
    ).toHaveCount(0);
    for (const width of [360, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(
        (
          await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
            .analyze()
        ).violations,
      ).toEqual([]);
      await page.screenshot({
        path: test.info().outputPath(`workspace-${width}.png`),
        fullPage: true,
      });
    }
  } finally {
    await readerContext.close();
  }
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back" }),
  ).toBeVisible();
});
