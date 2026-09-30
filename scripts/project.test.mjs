import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { initializeEnvironment } from "./project.mjs";

test("setup creates matching random credentials and preserves an existing environment", () => {
  const directory = mkdtempSync(join(tmpdir(), "lattice-setup-"));
  try {
    writeFileSync(join(directory, ".env.example"), "DJANGO_SECRET_KEY=CHANGE_ME\nPOSTGRES_PASSWORD=CHANGE_ME\nDATABASE_URL=postgresql://lattice:CHANGE_ME@localhost/lattice\n");
    assert.equal(initializeEnvironment(directory), true);
    const content = readFileSync(join(directory, ".env"), "utf8");
    const password = content.match(/POSTGRES_PASSWORD=(\w+)/)[1];
    assert.equal(password.length, 48);
    assert.ok(content.includes(`:${password}@`));
    assert.match(content, /DJANGO_SECRET_KEY=[a-f0-9]{96}/);
    assert.equal(content.includes("CHANGE_ME"), false);
    assert.equal(initializeEnvironment(directory), false);
    assert.equal(readFileSync(join(directory, ".env"), "utf8"), content);
  } finally {
    rmSync(directory, { recursive: true });
  }
});
