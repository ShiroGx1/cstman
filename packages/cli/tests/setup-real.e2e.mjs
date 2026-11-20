// The first run for real, on whatever OS runs this: the built CLI, the real
// Claude Code on PATH, the signed binaries from the pinned release, a home of
// its own. Not part of `npm test` (it downloads ~170 MB): CI runs it on
// Windows, macOS and Linux with `node --test tests/setup-real.e2e.mjs`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";

const cli = join(dirname(fileURLToPath(import.meta.url)), "..", "dist", "index.js");
const home = mkdtempSync(join(tmpdir(), "cstman-setup-real-"));

function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

const port = await freePort();
const env = { ...process.env, HOME: home, USERPROFILE: home, CSTMAN_HOME: join(home, ".cstman"), CSTMAN_LISTEN: `127.0.0.1:${port}`, CAVE_GATEWAY_URL: `http://127.0.0.1:${port}`, CAVE_API_URL: "http://127.0.0.1:9", CSTMAN_TELEMETRY: "0", CAVE_NO_KEYCHAIN: "1", NO_COLOR: "1", CI: "1" };
for (const key of ["CLAUDE_CONFIG_DIR", "CODEX_HOME", "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FORCE_COLOR"]) delete env[key];

function cstman(...argv) {
  const run = spawnSync(process.execPath, [cli, ...argv], { env, encoding: "utf8", timeout: 600_000 });
  return { code: run.status, out: `${run.stdout ?? ""}${run.stderr ?? ""}` };
}

const settingsPath = join(home, ".claude", "settings.json");

// Absolute paths a hook command runs or reads, quoted or bare.
function pathsIn(command) {
  const quoted = [...command.matchAll(/'([^']+)'|"([^"]+)"/g)].map((match) => match[1] ?? match[2]);
  return [...quoted, ...command.split(/\s+/)].map((part) => part.replace(/^& /, "")).filter((part) => isAbsolute(part));
}

test.after(() => {
  cstman("stop");
  rmSync(home, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 });
});

test("setup --dry-run names what it would do and writes nothing", () => {
  const dry = cstman("setup", "--dry-run", "--agents", "claude");
  assert.equal(dry.code, 0, dry.out);
  assert.match(dry.out, /Found .*Claude Code/);
  assert.match(dry.out, /DOWNLOAD +cstman-proxy/);
  assert.match(dry.out, /CREATE +~?.*settings\.json/);
  assert.match(dry.out, /Dry run: nothing was written\./);
  assert.equal(existsSync(settingsPath), false);
  assert.equal(existsSync(join(home, ".cstman", "bin")), false);
});

test("setup --yes downloads the runtime, wires Claude Code, and every hook path it wrote exists", { timeout: 900_000 }, () => {
  const out = cstman("setup", "--yes", "--agents", "claude");
  assert.equal(out.code, 0, out.out);
  assert.match(out.out, /✓ downloaded cstman-proxy/);
  assert.match(out.out, /✓ Claude Code wired/);
  assert.match(out.out, /✓ Ready\. Try: {2}\S.* claude/);
  assert.doesNotMatch(out.out, /checksum verified/, "the download is one line per binary, not the installer's own report");

  const exe = process.platform === "win32" ? ".exe" : "";
  for (const name of ["cstman-proxy", "cstman-mcp", "cstman-engine"]) assert.ok(existsSync(join(home, ".cstman", "bin", `${name}${exe}`)), `${name} installed`);

  const settings = JSON.parse(readFileSync(settingsPath, "utf8"));
  assert.equal(settings.env.ANTHROPIC_BASE_URL, `http://127.0.0.1:${port}/w/claude`);
  const commands = Object.values(settings.hooks ?? {}).flat().flatMap((entry) => entry.hooks ?? []).map((hook) => hook.command);
  assert.ok(commands.length > 0, "hooks written");
  const paths = commands.flatMap(pathsIn);
  assert.ok(paths.length > 0, `no absolute path found in: ${commands.join(" | ")}`);
  for (const path of paths) assert.ok(existsSync(path), `hook names a path that does not exist: ${path}`);
});

test("status and doctor read the install; off --all puts Claude Code's settings back", () => {
  const status = cstman("status");
  assert.equal(status.code, 0, status.out);
  assert.match(status.out, /output/);
  const doctor = cstman("doctor", "claude");
  assert.equal(JSON.parse(doctor.out.slice(doctor.out.indexOf("{"))).state, "installed", doctor.out);

  const off = cstman("off", "--all", "--yes");
  assert.equal(off.code, 0, off.out);
  const after = existsSync(settingsPath) ? JSON.parse(readFileSync(settingsPath, "utf8")) : {};
  assert.equal(after.env?.ANTHROPIC_BASE_URL, undefined);
  assert.equal(JSON.stringify(after).includes("cstman"), false, JSON.stringify(after));
});
