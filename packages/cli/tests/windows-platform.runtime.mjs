import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, mkdirSync, readdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { stubEnv } from "./harness/index.mjs";
import {
  binaryInstallFilename,
  commandHasPath,
  ensureCstmanHome,
  executableCandidateNames,
  generatedPluginInvocation,
  hookExecutableInvocation,
  hostShellInvocation,
  nativeHookInvocation,
  normalizeHookPath,
  quoteHookPath,
  removeAsideBinaries,
  replaceBinary,
  samePath,
  setupPlatform,
} from "../dist/index.js";
import { nativePipePath } from "../dist/native-pipe.js";
import { HOME_MARKERS, leaveHomeAclAlone, OWNED_HOME_ENTRIES, OWNED_HOME_SUFFIX, systemTool } from "../dist/home-acl.js";

test("CLI setup accepts Windows x64 and arm64", () => {
  assert.deepEqual(setupPlatform("win32", "x64"), { os: "win32", arch: "amd64" });
  assert.deepEqual(setupPlatform("win32", "arm64"), { os: "win32", arch: "arm64" });
  assert.equal(binaryInstallFilename("cstman-proxy", "win32"), "cstman-proxy.exe");
});

// Windows refuses to replace a running .exe (EPERM) but lets it be renamed.
test("an update moves a running Windows binary aside instead of failing with EPERM", () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-replace-"));
  const target = join(dir, "cstman-proxy.exe");
  const part = `${target}.part`;
  const windows = (from, to) => {
    if (to === target && existsSync(target)) throw Object.assign(new Error(`EPERM: operation not permitted, rename '${from}' -> '${to}'`), { code: "EPERM" });
    renameSync(from, to);
  };
  writeFileSync(target, "old");
  writeFileSync(part, "new");
  replaceBinary(part, target, "win32", windows);
  assert.equal(readFileSync(target, "utf8"), "new");
  const aside = readdirSync(dir).filter((name) => name !== "cstman-proxy.exe");
  assert.equal(aside.length, 1);
  assert.match(aside[0], /^cstman-proxy\.exe\.old-\d+-\d+$/);
  assert.equal(readFileSync(join(dir, aside[0]), "utf8"), "old");
  // A later install removes the aside copy once nothing runs it.
  removeAsideBinaries(dir);
  assert.deepEqual(readdirSync(dir), ["cstman-proxy.exe"]);

  // Locked so hard it cannot even move: a plain message, not a raw EPERM.
  writeFileSync(part, "newer");
  const locked = () => { throw Object.assign(new Error("EPERM: operation not permitted"), { code: "EPERM" }); };
  assert.throws(() => replaceBinary(part, target, "win32", locked), /^Error: cstman-proxy\.exe is in use and could not be replaced — run `cstman stop`/);
  assert.equal(readFileSync(target, "utf8"), "new");
  // Elsewhere an EPERM is not this and stays as it was.
  assert.throws(() => replaceBinary(part, target, "linux", windows), /EPERM/);
});

test("CLI recognizes Windows paths and PATHEXT without double extensions", () => {
  assert.equal(commandHasPath("C:\\Users\\cave\\cstman-proxy.exe"), true);
  assert.equal(commandHasPath(".\\bin\\cstman-proxy.exe"), true);
  assert.equal(commandHasPath("cstman-proxy"), false);
  assert.deepEqual(
    executableCandidateNames("cstman-proxy", "win32", ".EXE;.CMD;.EXE"),
    ["cstman-proxy.EXE", "cstman-proxy.CMD", "cstman-proxy"],
  );
  assert.deepEqual(
    executableCandidateNames("cstman-proxy.exe", "win32", ".EXE;.CMD"),
    ["cstman-proxy.exe"],
  );
});

// which() answers through PATHEXT, so with ~/.cstman/bin on PATH it names
// `cstman-proxy.EXE` where the install wrote `cstman-proxy.exe`: one file,
// and binariesBehindPin never saw an upgrader's binaries as behind.
test("Windows paths that differ only in case name the same file", () => {
  assert.equal(samePath("C:\\Users\\Jane\\.cstman\\bin\\cstman-proxy.EXE", "C:\\Users\\Jane\\.cstman\\bin\\cstman-proxy.exe", "win32"), true);
  assert.equal(samePath("C:\\Users\\Jane\\.cstman\\bin\\cstman-proxy.exe", "C:\\Users\\Jane\\bin\\cstman-proxy.exe", "win32"), false);
  assert.equal(samePath("/home/jane/.cstman/bin/cstman-proxy.EXE", "/home/jane/.cstman/bin/cstman-proxy.exe", "linux"), false);
});

test("CLI quotes Windows hook paths for PowerShell", () => {
  assert.equal(
    normalizeHookPath("C:\\Users\\cave\\AppData\\Roaming\\npm\\cstman.cmd", "win32"),
    "C:/Users/cave/AppData/Roaming/npm/cstman.cmd",
  );
  assert.equal(
    quoteHookPath("C:\\Users\\Jane Doe\\AppData\\Roaming\\npm\\cstman.cmd", "win32"),
    "'C:/Users/Jane Doe/AppData/Roaming/npm/cstman.cmd'",
  );
  assert.equal(
    quoteHookPath("C:\\Users\\Jane $mith\\it's `cave`\\cstman.cmd", "win32"),
    "'C:/Users/Jane $mith/it''s `cave`/cstman.cmd'",
  );
  assert.equal(normalizeHookPath("/usr/local/bin/cstman", "linux"), "/usr/local/bin/cstman");
});

test("CLI normalizes every path in Windows lifecycle hook commands", () => {
  assert.equal(
    nativeHookInvocation(
      "C:\\Users\\Jane Doe\\.cstman\\bin\\cstman-proxy.exe",
      "C:\\Program Files\\CSTMAN\\native-hook-fast.js",
      "claude",
      true,
      "win32",
      "C:\\Program Files\\nodejs\\node.exe",
    ),
    "& 'C:/Users/Jane Doe/.cstman/bin/cstman-proxy.exe' native-hook claude --adapter 'C:/Program Files/CSTMAN/native-hook-fast.js' --node 'C:/Program Files/nodejs/node.exe'",
  );
  assert.equal(
    nativeHookInvocation(
      "C:\\Program Files\\nodejs\\node.exe",
      "C:\\Program Files\\CSTMAN\\native-hook-fast.js",
      "claude",
      false,
      "win32",
    ),
    "& 'C:/Program Files/nodejs/node.exe' 'C:/Program Files/CSTMAN/native-hook-fast.js' native-hook claude",
  );
});

// Same vector as TestSocketPathWindowsMatchesNodeAdapters in
// proxy/internal/nativeruntime/server_windows_test.go: Go and Node must name the
// same pipe, or every Node hook silently loses the runtime.
test("native runtime pipe name matches the Go proxy for non-ASCII homes", () => {
  assert.equal(nativePipePath("C:\\Users\\İlker\\ΝΙΚΟΣ\\.cstman"), "\\\\.\\pipe\\cstman-native-4f3f9f7846224643");
  assert.equal(nativePipePath("C:/Users/Jane Doe/.cstman"), "\\\\.\\pipe\\cstman-native-0b9a73ef77a5671a");
});

// A drive root grants Authenticated Users Modify to everything below it, so a
// CSTMAN_HOME there left the credentials in it readable by every account.
test("a cstman home outside the Windows profile is private to this user", { skip: process.platform !== "win32" && "Windows ACLs" }, () => {
  const parent = mkdtempSync(join(tmpdir(), "cstman-acl-"));
  assert.equal(spawnSync("icacls", [parent, "/grant", "*S-1-5-11:(OI)(CI)M"]).status, 0);
  const saved = { CSTMAN_HOME: process.env.CSTMAN_HOME, USERPROFILE: process.env.USERPROFILE };
  Object.assign(process.env, { CSTMAN_HOME: join(parent, "home"), USERPROFILE: join(parent, "profile") });
  try { ensureCstmanHome(); } finally {
    for (const [key, value] of Object.entries(saved)) value === undefined ? delete process.env[key] : process.env[key] = value;
  }
  const acl = spawnSync("icacls", [join(parent, "home")], { encoding: "utf8" }).stdout;
  assert.doesNotMatch(acl, /Authenticated Users/);
  assert.match(acl, /NT AUTHORITY\\SYSTEM:\(OI\)\(CI\)\(F\)/);
  // A folder the user keeps other things in keeps its permissions.
  mkdirSync(join(parent, "work"));
  writeFileSync(join(parent, "work", "notes.txt"), "mine");
  process.env.CSTMAN_HOME = join(parent, "work");
  process.env.USERPROFILE = join(parent, "profile");
  try { ensureCstmanHome(); } finally {
    for (const [key, value] of Object.entries(saved)) value === undefined ? delete process.env[key] : process.env[key] = value;
  }
  assert.match(spawnSync("icacls", [join(parent, "work")], { encoding: "utf8" }).stdout, /Authenticated Users/);
});

// icacls /inheritance:r rewrites a folder's permissions and everything below
// it for good. Only a plain local folder holding nothing but cstman's own
// files is cstman's to rewrite.
test("a Windows home's permissions are rewritten only when cstman owns the folder", () => {
  const plain = { names: [], resolved: "D:\\cstman", link: false };
  const ours = ["bin", "run", "cloud.json", "cloud.json.123.tmp", "credentials", "cstman.db-wal", "proxy.log.1", ".cstman-sqlite-1", "provider-logins.json.lock",
    "modules.lock.json.123.a1b2c3.tmp", "cloud.json.123.a1b2c3.tmp", ".install.lock.123.1700000000000.stale", "cloud.json.telemetry.lock.123.1700000000000.stale"];
  assert.equal(leaveHomeAclAlone("D:\\cstman", plain), false);
  assert.equal(leaveHomeAclAlone("d:\\cstman\\", { ...plain, names: ours }), false);
  assert.equal(leaveHomeAclAlone("D:\\cstman", { ...plain, names: [...ours, "notes.txt"] }), true, "a user's file");
  assert.equal(leaveHomeAclAlone("D:\\cstman", { ...plain, names: ["binaries"] }), true, "a name that only starts like ours");
  assert.equal(leaveHomeAclAlone("D:\\tools", { ...plain, names: ["bin", "reports.xlsx", "run.bat", "credentials.txt", "usage-notes.md", "tmp"] }), true, "a tools folder");
  assert.equal(leaveHomeAclAlone("D:\\tools", { ...plain, names: ["cloud.json", "cli-tools", "hooks-backup", "mcp-servers"] }), true, "names that only continue like ours");
  assert.equal(leaveHomeAclAlone("D:\\tools", { ...plain, names: ["bin", "run", "tmp", "reports"] }), true, "generic names alone");
  assert.equal(leaveHomeAclAlone("D:\\cstman", { ...plain, names: ["cloud.json", ".install.lock"] }), false, "the install lock");
  assert.equal(leaveHomeAclAlone("D:\\cstman", { ...plain, names: ["cloud.json", "cloud.json.stale.txt"] }), true, "a name that only ends like ours");
  assert.equal(leaveHomeAclAlone("D:\\", { ...plain, resolved: "D:\\" }), true, "drive root");
  assert.equal(leaveHomeAclAlone("\\\\server\\share\\cstman", plain), true, "UNC path");
  assert.equal(leaveHomeAclAlone("Z:\\cstman", { ...plain, resolved: "\\\\server\\share\\cstman" }), true, "mapped network drive");
  assert.equal(leaveHomeAclAlone("D:\\cstman", { ...plain, link: true }), true, "junction");
});

// The proxy makes the same decision (proxy/internal/securehome); a name one
// side writes and the other does not know would leave that home broad.
test("the CLI and the proxy agree on what cstman writes into its home", () => {
  const go = readFileSync(new URL("../../../proxy/internal/securehome/securehome.go", import.meta.url), "utf8");
  const list = (name) => [...(new RegExp(`var ${name} = \\[\\]string\\{([\\s\\S]*?)\\n\\}`).exec(go)?.[1] ?? "").matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(list("ownedEntries"), OWNED_HOME_ENTRIES);
  assert.deepEqual(list("homeMarkers"), HOME_MARKERS);
  assert.equal(/var ownedSuffix = regexp\.MustCompile\(`([^`]+)`\)/.exec(go)?.[1], OWNED_HOME_SUFFIX.source);
});

// A bare whoami or icacls is looked up in the current directory first on
// Windows, so a copy planted in a project would run during setup.
test("Windows system tools run from System32", () => {
  assert.equal(systemTool("whoami", { SystemRoot: "C:\\WINDOWS" }), "C:\\WINDOWS\\System32\\whoami.exe");
  assert.equal(systemTool("icacls", {}), "C:\\Windows\\System32\\icacls.exe");
});

test("every Windows hook executable prefix uses PowerShell invocation", () => {
  assert.equal(
    hookExecutableInvocation("C:\\Users\\Jane Doe\\AppData\\Roaming\\npm\\cstman.CMD", undefined, "win32", false),
    "'C:/Users/Jane Doe/AppData/Roaming/npm/cstman.CMD'",
  );
  assert.equal(
    hookExecutableInvocation("C:\\Users\\Jane Doe\\AppData\\Roaming\\npm\\cstman.CMD", undefined, "win32"),
    "& 'C:/Users/Jane Doe/AppData/Roaming/npm/cstman.CMD'",
  );
  assert.equal(
    hookExecutableInvocation("/usr/local/bin/cstman", undefined, "darwin"),
    "'/usr/local/bin/cstman'",
  );
});

test("generated plugins bake Node target instead of a Windows CMD shim", () => {
  const root = mkdtempSync(join(tmpdir(), "cstman-plugin-shim-"));
  const packageDir = join(root, "node_modules", "@cstman-ai", "cli");
  mkdirSync(join(packageDir, "dist"), { recursive: true });
  const target = join(packageDir, "dist", "index.js");
  writeFileSync(target, "", "utf8");
  const shim = join(root, "cstman.CMD");
  writeFileSync(shim, '@IF EXIST "%~dp0\\node.exe" (\r\n  "%~dp0\\node.exe"  "%~dp0\\node_modules\\@cstman-ai\\cli\\dist\\index.js" %*\r\n) ELSE (\r\n  node  "%~dp0\\node_modules\\@cstman-ai\\cli\\dist\\index.js" %*\r\n)\r\n', "utf8");

  const invocation = generatedPluginInvocation(shim, "ignored.js", "win32");
  assert.equal(invocation.cmd, process.execPath);
  assert.deepEqual(invocation.pre, [target]);
});

test("stub preload path survives Node's own NODE_OPTIONS parsing", { skip: process.platform !== "win32" }, () => {
  // Node unescapes backslashes inside a quoted NODE_OPTIONS value, so an
  // unescaped Windows path reaches --require as `C:UsersRUNNER~1AppData…` and
  // every stub-backed suite dies in the preload with MODULE_NOT_FOUND before
  // the CLI under test runs a line. The space in the directory is why the
  // quotes cannot simply be dropped.
  const dir = join(mkdtempSync(join(tmpdir(), "cstman-stub-env-")), "Program Files", "bin");
  const env = stubEnv({ ...process.env }, dir);
  const result = spawnSync(process.execPath, ["-e", "process.stdout.write('ok')"], { env, encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "ok");
});

test("native PowerShell executes generated lifecycle hook commands", { skip: process.platform !== "win32" }, () => {
  const root = mkdtempSync(join(tmpdir(), "cstman-hook-smoke-"));
  const fixtureDir = join(root, "O'Brien space");
  mkdirSync(fixtureDir);
  const fixture = join(fixtureDir, "hook.js");
  const marker = join(root, "args.json");
  writeFileSync(fixture, 'require("node:fs").writeFileSync(process.env.CSTMAN_HOOK_MARKER, JSON.stringify(process.argv.slice(2)));\n', "utf8");
  const command = nativeHookInvocation(process.execPath, fixture, "claude", false, "win32");
  const result = spawnSync("powershell.exe", ["-NoProfile", "-Command", command], {
    env: { ...process.env, CSTMAN_HOOK_MARKER: marker },
    encoding: "utf8",
    windowsHide: true,
  });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(readFileSync(marker, "utf8")), ["native-hook", "claude"]);
});

// #1263: the shrink rewrite is handed back to the HOST to run in the HOST's own
// shell, which differs per host on Windows — Git Bash under Claude Code,
// PowerShell under the opencode plugin, cmd.exe under Gemini CLI. A quoted path
// is only a string literal in PowerShell, so the old single-quoted prefix died
// with `ParserError: Unexpected token 'shrink'` before the command ran.
test("a host-shell invocation is bare so PowerShell, bash and cmd all run it", () => {
  assert.equal(
    hostShellInvocation("C:\\Users\\jane\\AppData\\Roaming\\npm\\cstman.CMD", undefined, "win32"),
    "C:/Users/jane/AppData/Roaming/npm/cstman.CMD",
  );
  assert.equal(
    hostShellInvocation("C:\\Program Files\\nodejs\\node.exe", "C:\\npm\\cli\\dist\\index.js", "win32"),
    null,
    "a path needing quotes has no form all three shells accept — decline the rewrite instead",
  );
  // POSIX hosts all run sh/bash/zsh, where the quoted form is correct: unchanged.
  assert.equal(
    hostShellInvocation("/usr/local/bin/cstman", undefined, "darwin"),
    "'/usr/local/bin/cstman'",
  );
  assert.equal(
    hostShellInvocation("/usr/local/bin/node", "/opt/cli/dist/index.js", "linux"),
    "'/usr/local/bin/node' '/opt/cli/dist/index.js'",
  );
});
