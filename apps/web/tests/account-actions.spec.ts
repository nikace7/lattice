import { expect, test, type APIRequestContext } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function mailLink(request: APIRequestContext, recipient: string, route: string) {
  let link = "";
  await expect.poll(async () => {
    const response = await request.get("http://127.0.0.1:8026/api/v1/messages");
    const inbox = await response.json();
    const message = inbox.messages.find((item: { To: { Address: string }[] }) =>
      item.To.some((to) => to.Address === recipient),
    );
    if (!message) return false;
    const detail = await request.get(`http://127.0.0.1:8026/api/v1/message/${message.ID}`);
    const body = (await detail.json()).Text as string;
    link = body.match(new RegExp(`http://127\\.0\\.0\\.1:4411/account/${route}#token=[A-Za-z0-9_-]+`))?.[0] ?? "";
    return Boolean(link);
  }).toBe(true);
  return link;
}

test("invite a new teammate through email, then recover their password", async ({ page, browser, request }) => {
  const suffix = Date.now().toString(36);
  const owner = `inviter-${suffix}`;
  const guest = `guest-${suffix}`;
  const email = `${guest}@example.test`;
  const password = "reading-room-739!";
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Username", { exact: true }).fill(owner);
  await page.getByLabel("Email address", { exact: true }).fill(`${owner}@example.test`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await page.getByLabel("Workspace name").fill("Invited library");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.getByRole("link", { name: "People & access" }).click();
  await page.getByLabel("Invitation email").fill(email);
  await page.getByLabel("Invitation role").selectOption("VIEWER");
  await page.getByRole("button", { name: "Send invitation", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Invitation sent");
  const invitation = await mailLink(request, email, "invite");
  const guestContext = await browser.newContext({ baseURL: "http://127.0.0.1:4411" });
  try {
    const guestPage = await guestContext.newPage();
    await guestPage.goto(invitation);
    await guestPage.getByRole("button", { name: "Create an account" }).click();
    await guestPage.getByLabel("Username", { exact: true }).fill(guest);
    await guestPage.getByLabel("Email address", { exact: true }).fill(email);
    await guestPage.getByLabel("Password", { exact: true }).fill(password);
    await guestPage.getByRole("button", { name: "Create account", exact: true }).click();
    await guestPage.getByRole("button", { name: "Accept invitation" }).click();
    await expect(guestPage.getByRole("heading", { name: "Documents", exact: true })).toBeVisible();
    await expect(guestPage.getByRole("button", { name: "New collection" })).toHaveCount(0);
    await guestPage.goto(invitation);
    await guestPage.getByRole("button", { name: "Accept invitation" }).click();
    await expect(guestPage.getByRole("alert").filter({ hasText: "invalid or expired" })).toBeVisible();

    // Recovery in a separate browser must invalidate the previously signed-in session.
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByRole("link", { name: "Forgot your password?" }).click();
    await page.getByLabel("Email address").fill(email);
    await page.getByRole("button", { name: "Send recovery link" }).click();
    await expect(page.getByRole("status")).toContainText("If an active account");
    const reset = await mailLink(request, email, "reset");
    await page.goto(reset);
    await expect(page.getByLabel("New password")).toBeVisible();
    expect(new URL(page.url()).hash).toBe("");
    await page.setViewportSize({ width: 360, height: 900 });
    expect((await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByLabel("New password").fill("new-reading-room-942!");
    await page.getByRole("button", { name: "Save new password" }).click();
    await expect(page.getByRole("status")).toContainText("Password changed");
    await guestPage.goto("/");
    await expect(guestPage.getByRole("heading", { name: "Welcome back" })).toBeVisible();
    await page.getByRole("link", { name: "Return to sign in" }).click();
    await page.getByLabel("Username", { exact: true }).fill(guest);
    await page.getByLabel("Password", { exact: true }).fill("new-reading-room-942!");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("link", { name: /Invited library/ })).toBeVisible();
  } finally {
    await guestContext.close();
  }
});
