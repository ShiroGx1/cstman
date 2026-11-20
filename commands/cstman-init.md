---
description: Drop the always-on cstman activation rule into the current repo for every IDE agent
argument-hint: "[--dry-run|--force] [--only <agent>]"
---

Write the per-repo cstman rule files (Cursor, Windsurf, Cline, Copilot, AGENTS.md) into the current repo, then report the result.

How to run the init script — pick the first that applies:

1. If `src/tools/cstman-init.js` exists in the current repo (you are inside a cstman checkout), run: `node src/tools/cstman-init.js $ARGUMENTS`
2. Otherwise download and run the standalone script (it is self-contained and supports stdin execution): `curl -fsSL https://raw.githubusercontent.com/JuliusBrussee/cstman/main/src/tools/cstman-init.js | node - $ARGUMENTS`

Use `--dry-run` first if the user did not pass `--force`, so we never silently overwrite an existing rule file.
