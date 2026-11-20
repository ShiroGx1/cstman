# cstman — opencode plugin

Native opencode plugin. Mirrors the Claude Code hook architecture using
opencode's `session.created` + `tui.prompt.append` lifecycle hooks.

## What this ships

| File | Role |
|---|---|
| `plugin.js` | ESM Bun module. Default-exports an opencode `Plugin` factory (opencode 1.x, imported through `package.json` `main` when the `opencode.json` `plugin` entry names this directory). |
| `server.js` | opencode 2.x entry: `{ id, setup(ctx) }` that wires `plugin.js`'s hooks to the 2.x event, prompt and context APIs. 2.x loads it from the `plugins/cstman/` directory; 1.x never loads it. |
| `package.json` | Marks the directory as ESM and names `plugin.js` as its `main`. |
| `commands/*.md` | Slash-command prompt templates (`/cstman`, `/ultracave`, `/megacave`, `/cstman-commit`, …). |

The installer (`installer/install.js --only opencode`) copies these alongside
`src/hooks/cstman-config.js` (for the symlink-safe flag-write helpers, renamed
to `cstman-config.cjs` because this directory is `"type": "module"`) into
`~/.config/opencode/plugins/cstman/` and patches `opencode.json` with a
`"plugin"` array entry naming that directory (`./plugins/cstman`), the one
form both opencode 1.x and 2.x load.

## What it does

- `session.created` → writes the configured default mode to
  `~/.config/opencode/.cstman-active` via the same `safeWriteFlag` helper
  Claude Code uses (O_NOFOLLOW, atomic temp+rename, 0600 perms, symlink
  refusal, ownership check).
- `tui.prompt.append` → flips the flag in response to `/cstman`, `/ultracave`,
  `/megacave`, `/cstman off`, `/cstman-commit`, `/cstman-review`, `/cstman-compress`, and natural
  language ("turn on cstman", "stop cstman", "normal mode"). When a
  non-independent mode is active, appends a one-line reinforcement to keep
  cstman in the model's attention each turn.

## What it does NOT do

- **No statusline badge.** opencode's TUI does not expose a plugin-writable
  statusline. The flag file is at `~/.config/opencode/.cstman-active` if
  you want to surface mode in your shell prompt.
- **No system-prompt injection from `session.created`.** opencode's docs
  don't expose a return shape for that. The always-on cstman ruleset comes
  from `~/.config/opencode/AGENTS.md` (also written by the installer) so
  the rules load even when the plugin runtime is broken.

## Why no separate npm package

Plugin code reuses `cstman-config.js` from the main repo. Shipping as an
in-repo plugin avoids a second release cadence and a name collision with
the existing third-party `opencode-cstman` npm package.
