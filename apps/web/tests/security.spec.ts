import { expect, test } from "@playwright/test";

test("production CSP permits hydration and blocks scripts without the response nonce", async ({ page, request }) => {
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({ json: { user: null, csrfToken: "test" } }));
  // Inject into the HTML response: script-created elements can inherit strict-dynamic trust.
  await page.route("http://127.0.0.1:4411/", async (route) => {
    const response = await route.fetch();
    const html = await response.text();
    await route.fulfill({ response, body: html.replace("</body>", "<script>document.documentElement.dataset.untrustedScript = 'executed'</script></body>") });
  });
  const response = await page.goto("/");
  const policy = response!.headers()["content-security-policy"];
  expect(policy).toContain("'strict-dynamic'");
  expect(policy).not.toContain("'unsafe-eval'");
  expect(response!.headers()["cache-control"]).toContain("no-store");
  const nonce = policy.match(/'nonce-([^']+)'/)![1];
  const scriptNonces = await page.locator("script[nonce]").evaluateAll((scripts) => scripts.map((script) => script.nonce));
  expect(scriptNonces.length).toBeGreaterThan(0);
  expect(scriptNonces.every((value) => value === nonce)).toBe(true);
  await page.getByLabel("Password", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");
  await expect(page.locator("html")).not.toHaveAttribute("data-untrusted-script", "executed");
  const next = await request.get("/account/verify", { headers: { "x-nonce": "untrusted-client-nonce" } });
  expect(next.headers()["content-security-policy"]).not.toContain(nonce);
  expect(next.headers()["content-security-policy"]).not.toContain("untrusted-client-nonce");
});
