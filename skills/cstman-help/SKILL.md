---
name: cstman-help
description: >
  Quick-reference card for the three cstman skills and their commands.
  Trigger: /cstman-help or "cstman help".
---

# CSTMAN Help

Display this reference card when invoked. One-shot — do NOT change mode, write flag files, or persist anything. Output in cstman style.

## Modes

| Mode | Trigger | What change |
|------|---------|-------------|
| **cstman** | `/cstman` | The voice. Answer first, no fluff, every fact kept. Default. |
| **ultracst** | `/ultracst` (alias `/cstman ultra`) | Grammar stripped. Fragments, one word when enough, each fact once. |
| **megacst** | `/megacst` (alias `/cstman wenyan`) | Classical Chinese 文言文. Far fewer characters, technical terms verbatim. |

Mode stick until changed or session end.
`/cstman status` reports current mode without changing it. Claude Code and the standalone OpenCode plugin read stored state; other hosts answer from the conversation and mark it `(not tracked by this host)`.

## Skills

| Skill | Trigger | What it do |
|-------|---------|-----------|
| **cstman-commit** | `/cstman-commit` | Terse commit messages. Conventional Commits. ≤50 char subject. |
| **cstman-review** | `/cstman-review` | One-line PR comments: `L42: bug: user null. Add guard.` |
| **cstman-compress** | `/cstman-compress <file>` | Compress .md files to cstman prose. 33.2% fewer tokens on the repo's five test files. |
| **cstman-help** | `/cstman-help` | This card. |

## Deactivate

Say "stop cstman" or "normal mode". Resume anytime with `/cstman`.

## Language

Keep user's language by default — reply in the language user writes, never switch regardless of example text or multilingual context elsewhere. Compress the style, not the language. Technical terms, code, commands, commit types, and exact error strings stay verbatim unless user ask for translation.

## Configure Default Mode

Default mode = `cstman`. Change it:

**Environment variable** (highest priority):
```bash
export CSTMAN_DEFAULT_MODE=ultracst
```

**Config file** (`~/.config/cstman/config.json`):
```json
{ "defaultMode": "ultracst" }
```

For opt-in activation in Claude Code, set `defaultMode` to `manual`. Sessions start off; `/cstman` or `talk like cstman` activates cstman. `off` also disables bare-command activation. `manual` is a startup policy, not a mode. OpenCode still starts in cstman mode because its installer also supplies static activation rules.

Set `"off"` to suppress automatic and bare-command activation. Use `"manual"` when bare `/cstman` should activate.

Resolution: env var > repo config > user config > `cstman`. Legacy values `lite`, `full`, `ultra`, `wenyan*` still resolve.

## More

Full docs: https://github.com/JuliusBrussee/cstman
