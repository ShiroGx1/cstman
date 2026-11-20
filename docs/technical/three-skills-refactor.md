# Three skills, one mode model

Status: implemented in 3.1.0 (2026-10-02). Kept as the design record for the three-skill mode model.

## Goal

Six intensity levels become three skills that map 1:1 to stored modes. No per-level filtering of SKILL.md. Every embedded rule copy derives from the skill files. Old stored values keep working.

## Mode model

Stored mode ids: `cstman`, `ultracave`, `megacave`, `commit`, `review`, `compress`, `off`. `manual` stays a default-policy value only.

`cstman-config.js`:
- `VALID_MODES` = the list above. `VALID_DEFAULT_MODES` adds `manual`.
- New `canonicalMode(raw)` maps legacy values on every read: `lite`, `full` to `cstman`; `ultra` to `ultracave`; `wenyan`, `wenyan-lite`, `wenyan-full`, `wenyan-ultra` to `megacave`. Applied in `readFlag`, `resolveActiveMode`, `readSessionModeRaw`, `readSessionPrev`, `getDefaultMode` (config files and `CSTMAN_DEFAULT_MODE`). Writes always emit new ids. Legacy mirror keeps the never-`off` invariant.
- `canonicalModeLabel` and the `wenyan` storage alias go away.
- `skillPathCandidates(hookDir, skillId)` resolves `skills/<id>/SKILL.md` in the same three layouts as today.
- `loadRuleset(mode, hookDir)` replaces `loadFilteredRuleset`: read the file for the mode, strip frontmatter, return the whole body. One-shot modes keep banner-only behaviour.
- `thesisLine(mode, hookDir)`: first non-empty line after `# <id>`. Used for per-turn reinforcement. Fallback map of the three thesis strings when no file resolves.

## SessionStart (`cstman-activate.js`)

- Banner `CSTMAN MODE ACTIVE — mode: <id>`.
- Body = `loadRuleset(mode)`. Switch line names `/cstman`, `/ultracave`, `/megacave`, "stop cstman".
- Embedded fallback ruleset = thesis line plus the nine rule headlines, generated (see Copies). Keep the `cfg.x || stub` pattern for plugin-cache drift (#848).

## UserPromptSubmit (`cstman-parse.js`, `cstman-mode-tracker.js`)

- Parser accepts `/cstman`, `/cstman off`, `/cstman status`, `/ultracave`, `/megacave`, namespaced `/cstman:ultracave` and `/cstman:megacave`. Aliases still parse: `/cstman ultra` to `ultracave`, `/cstman wenyan*` to `megacave`, `/cstman lite|full` to `cstman`. Natural-language phrases unchanged, all resolve to `cstman`.
- `unresolved` notice lists the three commands instead of the level list.
- `REINFORCEMENT_RULES` table deleted. `reinforcementForMode(mode)` = `CSTMAN MODE ACTIVE (<id>). <thesis line> Technical terms, code, commands, paths, and errors stay exact.`
- Mode switch mid-session injects the full new skill body via `loadRuleset` (today's #975 path).
- One-shot prev/restore logic unchanged except for ids.

## Statusline (`.sh`, `.ps1`)

Whitelist new ids plus legacy ids. Render `cstman` as `[CSTMAN]`, `ultracave` as `[ULTRACAVE]`, `megacave` as `[MEGACAVE]`, one-shots as `[CSTMAN:COMMIT]` etc. Legacy values go through the same map. `verify_powershell_static` constants unchanged.

## Copies: generate, do not hand-maintain

`skills/compile.mjs` already emits CLI embeds from `skills/*/SKILL.md` plus `registry.json`. Extend it:
- Registry entries for `ultracave` and `megacave` (delivery `cli`, suite `output`).
- Emit `src/rules/cstman-activate.md` from the cstman skill: thesis line, nine rule headlines as bullets, switch and stop lines. This is the always-on IDE rule and the opencode `AGENTS.md` body.
- The OpenClaw bootstrap (`src/rules/cstman-openclaw-bootstrap.md` and the embedded copy in `installer/lib/openclaw.js`) and the MV3 directive (`extension/src/directive.js`) stay hand-synced; `tests/installer/rule-copies.test.mjs` and `extension/test/directive.test.mjs` fail on drift.
Hand edits that remain: `agents/cavecrew-*.md` ("CSTMAN-ultra ... No narration" becomes "Ultracave voice. One line in, one line out."), `skills/cstman-help/SKILL.md` card, opencode `commands/` stubs (add `ultracave.md`, `megacave.md`, drop level text from `cstman.md`), README, INSTALL, CLAUDE.md, `skills/cstman/README.md`.

## Tests

Update: `test_mode_tracker.py`, `test_cstman_parse.js`, `test_mode_tracker_ruleset.js`, `test_mode_tracker_stdin.js` (reinforcement pin), `test_hooks.py` (the `## Intensity` assertion), `test_repo_local_config.js`, `test_symlink_flag.js`, `test_cstman_stats.js`, `fixtures/mode-activation/cases.json`, `hooks/manual-mode.test.mjs`, `installer/opencode.test.mjs`, `extension/test/*`, `verify_repo.py` (frontmatter list gains two files).

New: legacy value migration (`wenyan-lite` session file resolves to `megacave`; `.cstman-active` holding `lite` resolves to `cstman`); `/ultracave` and `/megacave` parse; reinforcement derived from file; statusline badges for new ids; compile output equals checked-in generated files.

Regenerate `src/hooks/checksums.sha256`, plugin mirror, `dist/cstman.skill`, `packages/cli/src/agent-skills.generated.ts`.

## Evals

`evals/llm_run.py` on a gen-5 model: three skill arms vs the terse arm. Commit the snapshot. README numbers only from that run. One long agentic run checked for silence and level compliance (#1127, #1154, #1125).


## Risks

- Old statusline with new ids: whitelist rejects `ultracave`, renders nothing. Acceptable; changelog note.
- Old mode-tracker reading new ids from the mirror: injects the generic reinforcement. Fine.
- `MAX_FLAG_BYTES` sized for `wenyan-ultra`; `ultracave` is shorter.
- README "What you get" table must name both new skills or `verify_repo` fails.

## Mixed-version install (added after review)

Plugin hooks and standalone hooks can both be registered. A standalone
`cstman-activate.js` from before 3.1 does not recognise the new ids: on
`compact`/`resume` it re-derives the default and writes `full`, undoing an
`/ultracave` or `/megacave` roughly every other continuation while the plugin
hook writes the new id back. The release notes tell standalone users to re-run
the installer (`npx -y github:JuliusBrussee/cstman`) or remove the standalone
hooks. New code never writes legacy ids, so there is no in-code mitigation.
