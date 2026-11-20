# cstcrew

Decision guide. When to delegate to cstman subagents instead of doing the work inline.

## What it does

Tells main thread when to spawn a cstman-style subagent. Compact return
contracts can reduce repeated prose when results return to main context, but
effect depends on task, agent, and delegation count. This skill publishes no
universal reduction rate.

Three subagents:

| Subagent | Job | Use when |
|----------|-----|----------|
| `cstcrew-investigator` | Locate code (read-only) | "Where is X defined / what calls Y / list uses of Z" |
| `cstcrew-builder` | Surgical edit, 1-2 files | Scope is obvious, ≤2 files. Refuses 3+ file scope. |
| `cstcrew-reviewer` | Diff/file review | One-line findings with severity emoji |

Use vanilla `Explore` or `Code Reviewer` when you want prose, architecture commentary, or rationale. Use main thread directly for one-line answers and 3+ file refactors.

This skill is a decision guide, not a slash command. It activates when the conversation mentions delegation.

## How to invoke

Triggers on phrases like "delegate to subagent", "use cstcrew", "spawn investigator", "save context", "compressed agent output".

## Example chaining

Locate → fix → verify (most common):

1. `cstcrew-investigator` returns site list (`path:line`, symbol, note)
2. Main thread picks 1-2 sites, hands paths to `cstcrew-builder`
3. `cstcrew-reviewer` audits the resulting diff

Parallel scout: spawn 2-3 `cstcrew-investigator` calls in one message with different angles (defs, callers, tests). Aggregate in main.

## Model overrides

By default, `cstcrew-reviewer` and `cstcrew-investigator` pin `model: haiku` in their frontmatter; `cstcrew-builder` has no `model:` line (uses the API session default). Set env vars in your shell before launching Claude Code to override per-agent:

| Env var | Agent |
|---|---|
| `CAVECREW_REVIEWER_MODEL` | `cstcrew-reviewer` |
| `CAVECREW_BUILDER_MODEL` | `cstcrew-builder` |
| `CAVECREW_INVESTIGATOR_MODEL` | `cstcrew-investigator` |

Example: run reviewer on sonnet and keep others on default.

```sh
export CAVECREW_REVIEWER_MODEL=sonnet
```

Use the same model name strings you'd use in any Claude Code agent frontmatter (e.g. `haiku`, `sonnet`, `opus`).

Overrides patch only `model:` line in installed agent frontmatter; prompt body
stays untouched and continues receiving upstream updates. Only plugin installs
have local agent files to patch. Empty variables do nothing. Patch persists until
plugin update or reinstall.

## See also

- [`SKILL.md`](./SKILL.md): full decision matrix and output contracts
- [`agents/cstcrew-investigator.md`](../../agents/cstcrew-investigator.md)
- [`agents/cstcrew-builder.md`](../../agents/cstcrew-builder.md)
- [`agents/cstcrew-reviewer.md`](../../agents/cstcrew-reviewer.md)
- [CSTMAN README](../../README.md): repo overview
