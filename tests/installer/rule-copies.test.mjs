// Embedded copies of the always-on rule must match their sources byte for byte.
// Fix a failure by running `node skills/compile.mjs`, not by hand-editing a copy.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { activationRule } from "../../skills/activation-rule.mjs";

const require = createRequire(import.meta.url);
const read = (relative) => readFileSync(new URL(`../../${relative}`, import.meta.url), "utf8");

test("src/rules/cstman-activate.md is generated from skills/cstman/SKILL.md", () => {
  assert.equal(read("src/rules/cstman-activate.md"), activationRule(read("skills/cstman/SKILL.md")));
});

test("cstman-init.js embedded RULE_BODY equals src/rules/cstman-activate.md", () => {
  assert.equal(require("../../src/tools/cstman-init.js").RULE_BODY, read("src/rules/cstman-activate.md"));
});

test("openclaw embedded bootstrap fallback equals src/rules/cstman-openclaw-bootstrap.md", () => {
  const { loadBootstrapSnippet } = require("../../installer/lib/openclaw.js");
  assert.equal(loadBootstrapSnippet(null), read("src/rules/cstman-openclaw-bootstrap.md"));
});

test("always-on copies name the three skills and no retired level list", () => {
  for (const file of ["src/rules/cstman-activate.md", "src/rules/cstman-openclaw-bootstrap.md"]) {
    const body = read(file);
    assert.match(body, /Respond terse like smart cstman/, `${file}: sentinel`);
    for (const command of ["/cstman", "/ultracave", "/megacave"]) assert.ok(body.includes(command), `${file}: ${command}`);
    assert.doesNotMatch(body, /wenyan|lite\|full/, `${file}: retired level names`);
  }
});
