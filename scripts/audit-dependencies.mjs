import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const advisory = "GHSA-vfj7-8cjw-p6xm";
const lintPath = "apps__web>eslint-config-next>@next/eslint-plugin-next>fast-glob>micromatch>braces";

export function reviewAudit(report, now = new Date()) {
  if (!report?.advisories || typeof report.advisories !== "object" ||
      Array.isArray(report.advisories) || !report.metadata?.vulnerabilities || report.error) {
    throw new Error("Dependency audit did not return a complete report.");
  }
  const findings = Object.values(report.advisories);
  const counts = ["info", "low", "moderate", "high", "critical"].map((level) => report.metadata.vulnerabilities[level]);
  if (counts.some((count) => !Number.isInteger(count) || count < 0) ||
      counts.reduce((sum, count) => sum + count, 0) !== findings.length) {
    throw new Error("Dependency audit summary does not match its findings.");
  }
  const mitigated = findings.filter((item) =>
    item.github_advisory_id === advisory && item.module_name === "braces" &&
    now < new Date("2026-11-12T00:00:00Z") && item.findings?.length > 0 &&
    item.findings.every((finding) => finding.version === "3.0.3" &&
      finding.paths?.length > 0 && finding.paths.every((path) => path === lintPath))
  );
  return { mitigated, unresolved: findings.filter((item) => !mitigated.includes(item)) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // The exception is valid only while the installed dependency passes the mitigation test.
  const check = spawnSync(process.execPath, ["--test", "scripts/dependency-security.test.mjs"], { stdio: "inherit" });
  if (check.error || check.status !== 0) throw new Error("Dependency mitigation check failed.");
  if (!process.env.npm_execpath) throw new Error("Run through pnpm security:audit.");
  const audit = spawnSync(process.execPath, [process.env.npm_execpath, "audit", "--json"], { encoding: "utf8" });
  if (audit.error || ![0, 1].includes(audit.status)) throw new Error("Dependency audit failed to run.");
  const report = JSON.parse(audit.stdout);
  if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(report, null, 2));
  const { mitigated, unresolved } = reviewAudit(report);
  for (const item of mitigated) console.warn(`${item.github_advisory_id}: local string-parser depth mitigation; upstream unresolved. Exception expires 2026-11-12.`);
  for (const item of unresolved) console.error(`${item.github_advisory_id}: ${item.module_name} — ${item.title}`);
  console.log(`${unresolved.length} unresolved advisories; ${mitigated.length} visibly tracked local mitigations.`);
  if (unresolved.length) process.exitCode = 1;
}
