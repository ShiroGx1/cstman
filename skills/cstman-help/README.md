# cstman-help

Quick-reference card. One shot, no mode change.

## What it does

Prints a cheat sheet of all cstman modes, sibling skills, deactivation triggers, and how to set the default mode via env var or config file. One-shot display — does not flip the active mode, write flag files, or persist anything. Use when you forget the slash commands.

## How to invoke

```
/cstman-help
```

Also triggers on "cstman help", "what cstman commands", "how do I use cstman".

## Example output

```
Modes:
  /cstman              the voice (default)
  /ultracave            grammar stripped
  /megacave             classical Chinese
  /cstman status       report the mode, change nothing

Skills:
  /cstman-commit       terse Conventional Commits
  /cstman-review       one-line PR comments
  /cstman-compress     smaller Markdown memory files
  /cstman-stats        recorded token usage (savings unknown)

Deactivate:
  "stop cstman" or "normal mode"
```

## See also

- [`SKILL.md`](./SKILL.md) — full reference card
- [CSTMAN README](../../README.md) — repo overview
