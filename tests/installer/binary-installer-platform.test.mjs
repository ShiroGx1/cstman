import assert from "node:assert/strict";
import test from "node:test";

import {
  binaryInstallFilename,
  executableCandidateNames,
  targetPlatform,
} from "../../packages/shared/binary-installer/installer.mjs";

test("standalone binary installer supports Windows targets", () => {
  assert.deepEqual(targetPlatform("win32", "x64"), { os: "win32", arch: "amd64" });
  assert.deepEqual(targetPlatform("win32", "arm64"), { os: "win32", arch: "arm64" });
  assert.equal(binaryInstallFilename("cstman-mcp", "win32"), "cstman-mcp.exe");
  assert.equal(binaryInstallFilename("cstman-mcp", "darwin"), "cstman-mcp");
});

test("Windows PATH lookup respects PATHEXT and existing extensions", () => {
  assert.deepEqual(
    executableCandidateNames("cstman-mcp", "win32", ".EXE;.CMD;.EXE"),
    ["cstman-mcp.EXE", "cstman-mcp.CMD", "cstman-mcp"],
  );
  assert.deepEqual(
    executableCandidateNames("cstman-mcp.exe", "win32", ".EXE;.CMD"),
    ["cstman-mcp.exe"],
  );
});
