import { test } from "node:test";
import assert from "node:assert";
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const launcher = join(here, "cstman-browse.mjs");

test("launcher fails closed when explicit binary does not exist", async () => {
  const out = await runNode([launcher], {
    ...process.env,
    CSTMAN_BROWSE_BIN: join(tmpdir(), "cstman-browse-does-not-exist"),
  });
  assert.equal(out.code, 127);
  assert.match(out.stderr, /does not point to an executable/);
});

test("launcher honors CSTMAN_BROWSE_BIN explicit Go binary", { skip: process.platform === "win32" }, async () => {
  const dir = mkdtempSync(join(tmpdir(), "cstman-browse-bin-"));
  const stub = join(dir, "real-cstman-browse");
  writeFileSync(stub, "#!/bin/sh\nprintf 'ok'\n", { mode: 0o755 });
  const out = await runNode([launcher, "snapshot", "http://local"], { ...process.env, CSTMAN_BROWSE_BIN: stub });
  assert.equal(out.code, 0, out.stderr);
  assert.equal(out.stdout, "ok");
});

test("launcher skips its npm .bin shim and uses cached verified binary", { skip: process.platform === "win32" }, async () => {
  const root = mkdtempSync(join(tmpdir(), "cstman-browse-self-"));
  const npmBin = join(root, "node_modules", ".bin");
  const home = join(root, "home");
  mkdirSync(npmBin, { recursive: true });
  mkdirSync(join(home, "bin"), { recursive: true });
  symlinkSync(launcher, join(npmBin, "cstman-browse"));
  writeFileSync(join(home, "bin", "cstman-browse"), "#!/bin/sh\nprintf 'cached'\n", { mode: 0o755 });
  const env = { ...process.env, PATH: npmBin, CSTMAN_HOME: home };
  delete env.CSTMAN_BROWSE_BIN;
  const out = await runNode([launcher], env);
  assert.equal(out.code, 0, out.stderr);
  assert.equal(out.stdout, "cached");
});

function runNode(args, env) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { env });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("exit", (code) => resolve({ code, stdout, stderr }));
    child.on("error", reject);
  });
}
