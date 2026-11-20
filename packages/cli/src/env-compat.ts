import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

for (const [name, value] of Object.entries(process.env)) {
  if (!name.startsWith("CAVEMAN_")) continue;
  const renamed = `CSTMAN_${name.slice("CAVEMAN_".length)}`;
  if (process.env[renamed] === undefined) process.env[renamed] = value;
}

if (process.env.CSTMAN_HOME === undefined) {
  const home = homedir();
  const current = join(home, ".cstman");
  const legacy = join(home, ".caveman");
  if (!existsSync(current) && existsSync(legacy)) process.env.CSTMAN_HOME = legacy;
}
