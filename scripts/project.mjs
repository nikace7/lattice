import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export function initializeEnvironment(directory) {
  const target = join(directory, ".env");
  if (existsSync(target)) return false;
  const password = randomBytes(24).toString("hex");
  const content = readFileSync(join(directory, ".env.example"), "utf8")
    .replace("DJANGO_SECRET_KEY=CHANGE_ME", `DJANGO_SECRET_KEY=${randomBytes(48).toString("hex")}`)
    .replaceAll("CHANGE_ME", password);
  writeFileSync(target, content, { flag: "wx", mode: 0o600 });
  return true;
}

function run(command, args) {
  if (command === "pnpm") {
    if (!process.env.npm_execpath) throw new Error("Run this command through pnpm.");
    args = [process.env.npm_execpath, ...args];
    command = process.execPath;
  }
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", env: process.env });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} failed (exit ${result.status}).`);
}

function main(command) {
  switch (command) {
    case "setup":
      initializeEnvironment(root);
      for (const folder of ["storage", "models"]) mkdirSync(join(root, ".data", folder), { recursive: true });
      run("pnpm", ["install", "--frozen-lockfile"]);
      run("uv", ["sync", "--project", "backend", "--locked"]);
      console.log("Ready. Start Docker Desktop, then run pnpm dev. See README.md for host development.");
      break;
    case "dev":
      if (!existsSync(join(root, ".env"))) throw new Error("Run `pnpm run setup` first.");
      run("docker", ["compose", "up", "--build"]);
      break;
    case "verify":
      run("pnpm", ["lint"]);
      run("uv", ["run", "--project", "backend", "ruff", "format", "--check", "backend"]);
      run("pnpm", ["typecheck"]);
      run("uv", ["run", "--project", "backend", "python", "backend/manage.py", "check"]);
      run("uv", ["run", "--project", "backend", "python", "backend/manage.py", "makemigrations", "--check", "--dry-run"]);
      run("pnpm", ["test"]);
      run("pnpm", ["build"]);
      break;
    case "contracts":
      run("uv", ["run", "--project", "backend", "python", "backend/manage.py", "spectacular", "--file", "contracts/openapi.yaml", "--validate", "--fail-on-warn"]);
      run("pnpm", ["exec", "openapi-typescript", "contracts/openapi.yaml", "-o", "apps/web/src/lib/api.generated.ts"]);
      break;
    default:
      throw new Error(`Unknown project command: ${command}`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    main(process.argv[2]);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
