// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

afterEach(() => vi.unstubAllEnvs());

test("production CSP replaces supplied nonces and uses a fresh nonce per response", () => {
  vi.stubEnv("NODE_ENV", "production");
  const request = new NextRequest("http://localhost/", { headers: { "x-nonce": "attacker" } });
  const first = proxy(request);
  const second = proxy(request);
  const policy = first.headers.get("Content-Security-Policy")!;
  expect(policy).not.toContain("attacker");
  expect(policy).not.toContain("unsafe-eval");
  expect(policy.split(";").find((directive) => directive.trim().startsWith("script-src"))).not.toContain("unsafe-inline");
  expect(policy).toContain("object-src 'none'");
  expect(policy).toContain("frame-ancestors 'none'");
  expect(policy).not.toEqual(second.headers.get("Content-Security-Policy"));
  expect(first.headers.get("x-middleware-request-content-security-policy")).toBe(policy);
  expect(first.headers.get("Cache-Control")).toBe("private, no-store");
});

test("development allows its debugger without weakening production", () => {
  vi.stubEnv("NODE_ENV", "development");
  const policy = proxy(new NextRequest("http://localhost/")).headers.get("Content-Security-Policy");
  expect(policy).toContain("'unsafe-eval'");
  expect(policy).not.toContain("upgrade-insecure-requests");
});
