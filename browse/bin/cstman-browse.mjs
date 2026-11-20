#!/usr/bin/env node
// Launcher for cstman-browse. The driver itself is the prebuilt Go
// `cstman-browse` binary; this shim only locates and execs it, forwarding stdio
// for MCP hosts and CLI direct subcommands.
//
import { spawn } from "node:child_process";
import { existsSync, realpathSync } from "node:fs";
import { basename, delimiter, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ensureBinary } from "./binary-installer.generated.mjs";

let bin;
const launcher = realpathSync(fileURLToPath(import.meta.url));
const explicit = process.env.CSTMAN_BROWSE_BIN;
if (explicit && existsSync(explicit) && realpathSync(explicit) === launcher) {
  process.stderr.write(`cstman-browse: CSTMAN_BROWSE_BIN must point to the Go binary, not the npm launcher\n`);
  process.exit(127);
}
const originalPath = process.env.PATH;
process.env.PATH = withoutOwnNpmBin(originalPath);
try {
  bin = await ensureBinary({ name: "cstman-browse", envVar: "CSTMAN_BROWSE_BIN" });
} catch (error) {
  process.stderr.write(`cstman-browse: ${error.message}\n`);
  process.exit(127);
} finally {
  if (originalPath === undefined) delete process.env.PATH;
  else process.env.PATH = originalPath;
}
const child = spawn(bin, process.argv.slice(2), { stdio: "inherit" });

function withoutOwnNpmBin(value = "") {
  return value.split(delimiter).filter((directory) => {
    if (!directory) return false;
    const absolute = resolve(directory);
    if (basename(absolute).toLowerCase() === ".bin" &&
        basename(dirname(absolute)).toLowerCase() === "node_modules") return false;
    try {
      return realpathSync(resolve(absolute, "cstman-browse")) !== launcher;
    } catch {
      return true;
    }
  }).join(delimiter);
}

child.on("error", (err) => {
  if (err.code === "ENOENT") {
    process.stderr.write(`cstman-browse: verified binary disappeared before launch (${bin})\n`);
    process.exit(127);
  }
  process.stderr.write(`cstman-browse: ${err.message}\n`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});
