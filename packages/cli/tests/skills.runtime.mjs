import { test } from "node:test";
import assert from "node:assert";
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, existsSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cli = join(here, "..", "dist", "index.js");
const packageParent = join(here, "..", "..");
const canonicalSkillsRoot = [join(packageParent, "skills"), join(packageParent, "..", "skills")]
  .find((candidate) => existsSync(join(candidate, "registry.json")));
assert.ok(canonicalSkillsRoot, "canonical skills registry must exist beside public/ or packages/");
const canonicalLearn = join(canonicalSkillsRoot, "cstman-learn", "SKILL.md");
const canonicalCSTMAN = join(canonicalSkillsRoot, "cstman", "SKILL.md");
const canonicalExplore = join(canonicalSkillsRoot, "cstman-explore", "SKILL.md");

function run(extraArgs, extraEnv = {}) {
  const env = { ...process.env, NO_COLOR: "1", ...extraEnv };
  return new Promise((resolve, reject) => {
    const child = spawn("node", [cli, "skills", ...extraArgs], { env });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("exit", (code) => resolve({ code, stdout, stderr }));
    child.on("error", reject);
    child.stdin.end();
  });
}

function writeEngineStub() {
  const dir = mkdtempSync(join(tmpdir(), "cave-skills-engine-"));
  const bin = join(dir, "cstman-engine");
  writeFileSync(bin, `#!/usr/bin/env node
import { writeFileSync } from "node:fs";
const file = process.argv[5];
if (process.argv[2] !== "pixel" || process.argv[3] !== "render" || process.argv[4] !== "--dense" || !file) process.exit(2);
writeFileSync(file + ".px1.png", Buffer.from("png"));
console.log(JSON.stringify({ width: 10, height: 10, charsRendered: 10, droppedChars: 0, estTokens: 400 }));
console.log(JSON.stringify({ summary: true, pages: 1, textEstTokens: 5000, imageEstTokens: 400 }));
`, { mode: 0o755 });
  return bin;
}

// `cstman skills install --dir <tmp>` writes the skill, byte-identical to the
// canonical artifact (the drift guard — the binary embeds a copy).
test("skills install writes cstman-learn SKILL.md, matching the canonical artifact", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-"));
  const out = await run(["install", "--dir", dir, "--no-pixel"]);
  assert.equal(out.code, 0, `skills install exited ${out.code}: ${out.stderr}`);
  const dest = join(dir, "SKILL.md");
  assert.ok(existsSync(dest), "must write SKILL.md");
  const written = readFileSync(dest, "utf8");
  assert.match(written, /^---\nname: cstman-learn\n/, "valid skill frontmatter");
  assert.match(written, /net-token-negative gate/, "carries the net-token-negative gate");
  assert.match(written, /never make the agent dumber/i, "carries the dumber-guard");
  assert.equal(
    written,
    readFileSync(canonicalLearn, "utf8"),
    "the CLI-embedded skill must stay byte-identical to public/skills/cstman-learn/SKILL.md",
  );
});

test("skills install writes cstman SKILL.md, matching the canonical artifact", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-cstman-"));
  const out = await run(["install", "cstman", "--dir", dir, "--no-pixel"]);
  assert.equal(out.code, 0, `cstman install exited ${out.code}: ${out.stderr}`);
  const dest = join(dir, "SKILL.md");
  assert.ok(existsSync(dest), "must write SKILL.md");
  const written = readFileSync(dest, "utf8");
  assert.match(written, /^---\nname: cstman\n/, "valid skill frontmatter");
  assert.equal(
    written,
    readFileSync(canonicalCSTMAN, "utf8"),
    "the CLI-embedded skill must stay byte-identical to public/skills/cstman/SKILL.md",
  );
});

test("skills install writes cstman-explore SKILL.md, matching canonical artifact", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-explore-"));
  const out = await run(["install", "cstman-explore", "--agent", "claude", "--dir", dir, "--no-pixel"]);
  assert.equal(out.code, 0, `explore skill install exited ${out.code}: ${out.stderr}`);
  const dest = join(dir, "SKILL.md");
  assert.ok(existsSync(dest), "must write SKILL.md");
  const written = readFileSync(dest, "utf8");
  assert.match(written, /^---\nname: cstman-explore\n/, "frontmatter name must match directory");
  assert.match(written, /IN PARALLEL/, "must carry parallel-call contract");
  assert.match(written, /ONLY an evidence block/, "must carry citation-only contract");
  assert.equal(
    written,
    readFileSync(canonicalExplore, "utf8"),
    "CLI-embedded skill must stay byte-identical to public/skills/cstman-explore/SKILL.md",
  );
});

// Codex gets the skill as a standard SKILL.md directory.
test("skills install --agent codex writes a skill directory", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-codex-"));
  const out = await run(["install", "--agent", "codex", "--dir", dir, "--no-pixel"]);
  assert.equal(out.code, 0, `codex install exited ${out.code}: ${out.stderr}`);
  assert.ok(existsSync(join(dir, "SKILL.md")), "must write the codex skill file");
});

test("skills install cstman-explore --agent codex fails closed with unchanged message", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-explore-codex-"));
  const out = await run(["install", "cstman-explore", "--agent", "codex", "--dir", dir, "--no-pixel"]);
  assert.equal(out.code, 2, "codex explorer install must fail closed");
  assert.match(
    out.stderr,
    /cstman explore: only --agent claude is wired today \(codex needs verified transcript isolation first\)\. got: codex/,
  );
  assert.ok(!existsSync(join(dir, "SKILL.md")), "guard must run before writing");
});

test("skills install auto-pixels when the engine renders a profitable skill", async () => {
  const engine = writeEngineStub();
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-pixel-"));
  const out = await run(["install", "cstman", "--dir", dir], { CSTMAN_ENGINE_BIN: engine });
  assert.equal(out.code, 0, `pixel install exited ${out.code}: ${out.stderr}`);
  const written = readFileSync(join(dir, "SKILL.md"), "utf8");
  assert.match(written, /^---\nname: cstman\n[\s\S]*?<!-- cstman-pixel v1 sha256:[a-f0-9]{64} -->/);
  assert.match(written, /SKILL\.px1\.png/);
  assert.equal(readFileSync(join(dir, "SKILL.orig.md"), "utf8"), readFileSync(canonicalCSTMAN, "utf8"));
  assert.ok(existsSync(join(dir, "SKILL.px1.png")), "pixel install must move page into skill dir");
  assert.match(out.stderr, /Installed pixel form/);
  assert.match(out.stderr, /inferred/);
});

// An unknown skill name fails closed (non-zero, no file).
test("skills install of an unknown skill fails closed", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-skill-unknown-"));
  const out = await run(["install", "does-not-exist", "--dir", dir]);
  assert.notEqual(out.code, 0, "unknown skill must not be installed");
  assert.ok(!existsSync(join(dir, "SKILL.md")), "no file may be written for an unknown skill");
});

test("skills list --json exposes closed metadata and deterministic suites", async () => {
  const out = await run(["list", "--json"]);
  assert.equal(out.code, 0, out.stderr);
  const value = JSON.parse(out.stdout);
  assert.deepEqual(
    value.suites["agent-native"],
    ["cstman-setup", "cstman-discover", "cstman-evidence-review", "cstman-optimize", "cstman-manage"],
  );
  assert.deepEqual(
    value.skills.map((skill) => skill.id).sort(),
    [
      "cstman",
      "cstman-discover",
      "cstman-evidence-review",
      "cstman-explore",
      "cstman-learn",
      "cstman-manage",
      "cstman-optimize",
      "cstman-setup",
      "megacst",
      "ultracst",
    ],
  );
});

test("skills preview returns canonical content without writing", async () => {
  const out = await run(["preview", "cstman-evidence-review"]);
  assert.equal(out.code, 0, out.stderr);
  assert.equal(out.stdout, readFileSync(join(canonicalSkillsRoot, "cstman-evidence-review", "SKILL.md"), "utf8"));
});

test("cstman-optimize uses report-only observations and cannot select retired money ids", () => {
  const skill = readFileSync(join(canonicalSkillsRoot, "cstman-optimize", "SKILL.md"), "utf8");
  assert.match(skill, /report_only_observations/);
  for (const id of ["context-window-profile", "tool-catalog-profile", "tool-output-size-profile", "exploration-load-profile"]) {
    assert.match(skill, new RegExp(`\\b${id}\\b`), `${id} must be handled as an exact report-only observation`);
  }
  assert.match(skill, /explicit operator choice/i);
  assert.match(skill, /paired eval/i);
  assert.match(skill, /Never select or apply these retired ids:[\s\S]*context-window-bloat[\s\S]*tool-catalog-utilization[\s\S]*verbose-tool-output/);
  assert.doesNotMatch(skill, /savings_usd_base|Inferred headroom|\$<[^>]+>\/day/);
});

test("agent-native suite installs every canonical skill byte-identically", async () => {
  const dir = mkdtempSync(join(tmpdir(), "cave-agent-native-suite-"));
  const out = await run(["install", "--suite", "agent-native", "--agent", "claude", "--dir", dir, "--no-pixel"]);
  assert.equal(out.code, 0, out.stderr);
  for (const id of ["cstman-setup", "cstman-discover", "cstman-evidence-review", "cstman-optimize", "cstman-manage"]) {
    assert.equal(
      readFileSync(join(dir, id, "SKILL.md"), "utf8"),
      readFileSync(join(canonicalSkillsRoot, id, "SKILL.md"), "utf8"),
      `${id} must stay canonical`,
    );
  }
});

test("skills import creates an unevaluated non-published draft with bounded deterministic transforms", async () => {
  const source = mkdtempSync(join(tmpdir(), "cave-skill-import-source-"));
  writeFileSync(join(source, "SKILL.md"), `---
name: imported-check
description: Use when a user asks to check imported behavior.
---

# Imported check

Inspect existing behavior.

Inspect existing behavior.

Preserve validation.

Stop when focused checks pass.
`);
  const scripts = join(source, "scripts");
  mkdirSync(scripts);
  writeFileSync(join(scripts, "check.sh"), "#!/bin/sh\nexit 0\n");
  const parent = mkdtempSync(join(tmpdir(), "cave-skill-import-out-"));
  const target = join(parent, "draft");
  const out = await run(["import", source, "--out", target, "--json"]);
  assert.equal(out.code, 0, out.stderr);
  const response = JSON.parse(out.stdout);
  assert.equal(response.target, target);
  assert.equal(response.manifest.schema, "cstman.skill-import.v1");
  assert.equal(response.manifest.evidence_status, "unevaluated");
  assert.equal(response.manifest.publication.status, "blocked");
  assert.equal(response.manifest.transformations.exact_duplicate_blocks_removed, 1);
  assert.equal(response.manifest.activation.status, "detected_needs_review");
  assert.equal(response.manifest.stop_condition.status, "inferred_needs_review");
  const imported = readFileSync(join(target, "SKILL.md"), "utf8");
  assert.equal((imported.match(/Inspect existing behavior\./g) ?? []).length, 1);
  assert.equal(readFileSync(join(target, "scripts", "check.sh"), "utf8"), "#!/bin/sh\nexit 0\n");
  const before = readFileSync(join(target, "import.json"));
  const repeated = await run(["import", source, "--out", target]);
  assert.equal(repeated.code, 2);
  assert.match(repeated.stderr, /refusing overwrite/);
  assert.deepEqual(readFileSync(join(target, "import.json")), before);
});

test("skills import dry-run writes nothing and rejects credential-shaped material", async () => {
  const source = mkdtempSync(join(tmpdir(), "cave-skill-import-secret-"));
  writeFileSync(join(source, "SKILL.md"), `---
name: unsafe-import
description: Use when testing importer rejection.
---

Use token sk-abcdefghijklmnopqrstuvwxyz0123456789.
Stop after proof.
`);
  const target = join(mkdtempSync(join(tmpdir(), "cave-skill-import-dry-")), "draft");
  const out = await run(["import", source, "--out", target, "--dry-run", "--json"]);
  assert.equal(out.code, 2);
  assert.match(out.stderr, /credential-shaped material/);
  assert.ok(!existsSync(target));
});

// Bare `skills` (no/unknown subcommand) is a usage error, never a hang.
test("skills with no subcommand prints usage and exits non-zero", async () => {
  const out = await run([]);
  assert.notEqual(out.code, 0, "bare skills must exit non-zero");
  assert.match(out.stderr, /usage: cstman skills/);
});
