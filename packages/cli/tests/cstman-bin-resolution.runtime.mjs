import { test } from "node:test";
import assert from "node:assert";
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const cli = join(dirname(fileURLToPath(import.meta.url)), "..", "dist", "index.js");

// The missing-binary panels tell users to build into ~/.cstman/bin — so the CLI
// must actually find binaries there without a PATH edit. `cstman stats` shells to
// cstman-proxy; a stub in $CSTMAN_HOME/bin (NOT on PATH) must be what runs.
test("cstman binaries resolve from ~/.cstman/bin without a PATH entry", async () => {
  const home = mkdtempSync(join(tmpdir(), "cave-binres-"));
  const binDir = join(home, "bin");
  mkdirSync(binDir, { recursive: true });
  writeFileSync(join(binDir, "cstman-proxy"), `#!/bin/sh\nif [ "$1" = "stats" ]; then printf '{"resolved_from":"cstman-home-bin"}'; fi\n`, { mode: 0o755 });

  const env = { ...process.env, NO_COLOR: "1", CSTMAN_HOME: home };
  delete env.CSTMAN_PROXY_BIN;
  const out = await new Promise((resolve, reject) => {
    const child = spawn("node", [cli, "stats"], { env });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("exit", (code) => resolve({ code, stdout, stderr }));
    child.on("error", reject);
  });
  assert.equal(out.code, 0, `stats exited ${out.code}: ${out.stderr}`);
  assert.match(out.stdout, /cstman-home-bin/, "stats must run the ~/.cstman/bin binary");
});

// The explicit env override must still win over ~/.cstman/bin.
test("CSTMAN_PROXY_BIN overrides the ~/.cstman/bin fallback", async () => {
  const home = mkdtempSync(join(tmpdir(), "cave-binres2-"));
  const binDir = join(home, "bin");
  mkdirSync(binDir, { recursive: true });
  writeFileSync(join(binDir, "cstman-proxy"), `#!/bin/sh\nprintf 'WRONG'\n`, { mode: 0o755 });
  const override = join(home, "override-proxy");
  writeFileSync(override, `#!/bin/sh\nif [ "$1" = "stats" ]; then printf '{"resolved_from":"env-override"}'; fi\n`, { mode: 0o755 });

  const env = { ...process.env, NO_COLOR: "1", CSTMAN_HOME: home, CSTMAN_PROXY_BIN: override };
  const out = await new Promise((resolve, reject) => {
    const child = spawn("node", [cli, "stats"], { env });
    let stdout = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.on("exit", (code) => resolve({ code, stdout }));
    child.on("error", reject);
  });
  assert.equal(out.code, 0);
  assert.match(out.stdout, /env-override/, "the env override must win");
});
