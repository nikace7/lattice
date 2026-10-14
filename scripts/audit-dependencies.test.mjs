import assert from "node:assert/strict";
import test from "node:test";
import { reviewAudit } from "./audit-dependencies.mjs";

const finding = {
  github_advisory_id: "GHSA-vfj7-8cjw-p6xm", module_name: "braces",
  findings: [{ version: "3.0.3", paths: ["apps__web>eslint-config-next>@next/eslint-plugin-next>fast-glob>micromatch>braces"] }],
};
const counts = { info: 0, low: 0, moderate: 0, high: 0, critical: 0 };
const report = (item) => ({ advisories: { one: item }, metadata: { vulnerabilities: { ...counts, high: 1 } } });
const now = new Date("2026-10-12T00:00:00Z");

test("audit exception is exact, dev-only and time limited", () => {
  assert.equal(reviewAudit(report(finding), now).mitigated.length, 1);
  assert.equal(reviewAudit(report(finding), new Date("2026-11-12")).unresolved.length, 1);
  assert.equal(reviewAudit(report({ ...finding, github_advisory_id: "new-advisory" }), now).unresolved.length, 1);
  assert.equal(reviewAudit(report({ ...finding, findings: [{ version: "3.0.3", paths: ["apps__web>next>braces"] }] }), now).unresolved.length, 1);
  assert.equal(reviewAudit(report({ ...finding, findings: [] }), now).unresolved.length, 1);
});

test("audit fails closed on network or malformed responses", () => {
  assert.throws(() => reviewAudit({ error: "offline" }, now));
  assert.throws(() => reviewAudit({}, now));
  assert.throws(() => reviewAudit({ advisories: {}, metadata: { vulnerabilities: { ...counts, high: 1 } } }, now));
  assert.throws(() => reviewAudit({ advisories: [], metadata: { vulnerabilities: counts } }, now));
  assert.throws(() => reviewAudit({ advisories: {}, metadata: { vulnerabilities: {} } }, now));
  assert.deepEqual(reviewAudit({ advisories: {}, metadata: { vulnerabilities: counts } }, now), { mitigated: [], unresolved: [] });
});
