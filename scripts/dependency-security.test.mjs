import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const web = createRequire(new URL("../apps/web/package.json", import.meta.url));
const config = createRequire(web.resolve("eslint-config-next"));
const plugin = createRequire(config.resolve("@next/eslint-plugin-next"));
const glob = createRequire(plugin.resolve("fast-glob"));
const match = createRequire(glob.resolve("micromatch"));
const braces = match("braces");

test("lint glob dependency rejects excessive nested input before recursive walking", () => {
  for (const pattern of ["{".repeat(256) + "a,b" + "}".repeat(256), "(".repeat(256), "{(".repeat(128)]) {
    for (const method of ["parse", "compile", "expand", "stringify"]) {
      assert.throws(() => braces[method](pattern), { name: "SyntaxError", message: /nesting/ });
    }
  }
  assert.deepEqual(braces.expand("src/{app,components}/**/*.{ts,tsx}"), [
    "src/app/**/*.ts", "src/app/**/*.tsx", "src/components/**/*.ts", "src/components/**/*.tsx",
  ]);
});
