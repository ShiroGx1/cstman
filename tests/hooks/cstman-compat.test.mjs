import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { parseModeChange } = require("../../src/hooks/cstman-parse.js");

test("legacy /caveman commands and prose still switch CSTMAN mode", () => {
  const options = { getDefaultMode: () => "cstman" };
  assert.deepEqual(parseModeChange("/caveman", options), { action: "set", mode: "cstman" });
  assert.deepEqual(parseModeChange("/caveman off", options), { action: "clear" });
  assert.deepEqual(parseModeChange("stop caveman", options), { action: "clear" });
});
