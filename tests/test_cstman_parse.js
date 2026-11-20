#!/usr/bin/env node
// Tests for the shared mode-change parser (#602), src/hooks/cstman-parse.js.
// cstman-mode-tracker.js and the opencode plugin both consume this module —
// these tests exercise it directly (unit-level) and also check that its
// verdicts line up with what the real tracker.js hook does for the same
// prompts (parity), so the two callers can't silently drift apart again.
//
// Run: node tests/test_cstman_parse.js

const fs = require('fs');
const path = require('path');
const os = require('os');
const assert = require('assert');
const { spawnSync } = require('child_process');

const { parseModeChange, INDEPENDENT_MODES } = require('../src/hooks/cstman-parse');

const HOOK_PATH = path.resolve(__dirname, '..', 'src', 'hooks', 'cstman-mode-tracker.js');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    failed++;
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
  }
}

console.log('cstman-parse (shared mode-change parser) tests\n');

const defaultCSTMAN = { getDefaultMode: () => 'cstman' };
const defaultOff = { getDefaultMode: () => 'off' };
const MODE_OF = {
  '/ultracave': 'ultracave', '/cstman:ultracave': 'ultracave',
  '/megacave': 'megacave', '/cstman:megacave': 'megacave',
};

test('status uses one read-only verdict for literal and expanded commands', () => {
  const options = { getDefaultMode: () => { throw new Error('status must not resolve a default'); } };
  for (const prompt of ['/cstman status', '/cstman:cstman status', '/cstman status.']) {
    assert.deepStrictEqual(parseModeChange(prompt, options), { action: 'status' });
  }
  assert.deepStrictEqual(parseModeChange('Activate cstman mode: status\n\nIf no argument given, use cstman.', {
    ...options, expandedTpl: true,
  }), { action: 'status' });
  assert.strictEqual(parseModeChange('What does `/cstman status` do?', options), null);
});

test('manual startup policy permits explicit activation but is not a mode', () => {
  const options = { getDefaultMode: () => 'manual', expandedTpl: true };
  for (const prompt of ['/cstman', 'talk like cstman', 'Activate cstman mode: \n\nIf no argument given, use cstman.']) {
    assert.deepStrictEqual(parseModeChange(prompt, options), { action: 'set', mode: 'cstman' });
  }
  assert.deepStrictEqual(parseModeChange('/cstman manual', options), { action: 'unresolved' });
  assert.strictEqual(parseModeChange('ordinary request', options), null);
});

// ---------- basic unit coverage ----------

test('empty/whitespace prompt is a no-op', () => {
  assert.strictEqual(parseModeChange('', defaultCSTMAN), null);
  assert.strictEqual(parseModeChange('   ', defaultCSTMAN), null);
});

test('/ultracave and /megacave set their own mode, bare or namespaced', () => {
  for (const [prompt, mode] of [
    ['/ultracave', 'ultracave'], ['/cstman:ultracave', 'ultracave'],
    ['/megacave', 'megacave'], ['/cstman:megacave', 'megacave'],
  ]) {
    assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'set', mode }, prompt);
    // A configured default never overrides the command's own mode.
    assert.deepStrictEqual(parseModeChange(prompt, defaultOff), { action: 'set', mode }, prompt);
  }
});

test('/cstman <arg> accepts the three mode names', () => {
  for (const mode of ['cstman', 'ultracave', 'megacave']) {
    assert.deepStrictEqual(parseModeChange('/cstman ' + mode, defaultCSTMAN), { action: 'set', mode });
  }
});

test('legacy level names still parse as aliases of the three modes', () => {
  for (const [arg, mode] of [
    ['lite', 'cstman'], ['full', 'cstman'], ['ultra', 'ultracave'],
    ['wenyan', 'megacave'], ['wenyan-lite', 'megacave'],
    ['wenyan-full', 'megacave'], ['wenyan-ultra', 'megacave'],
  ]) {
    assert.deepStrictEqual(parseModeChange('/cstman ' + arg, defaultCSTMAN), { action: 'set', mode }, arg);
  }
});

test('/ultracave and /megacave take the same off/status words as /cstman', () => {
  for (const cmd of ['/ultracave', '/cstman:ultracave', '/megacave', '/cstman:megacave']) {
    for (const word of ['off', 'stop', 'disable', 'off.']) {
      assert.deepStrictEqual(parseModeChange(`${cmd} ${word}`, defaultCSTMAN), { action: 'clear' }, `${cmd} ${word}`);
    }
    assert.deepStrictEqual(parseModeChange(`${cmd} status`, defaultCSTMAN), { action: 'status' }, `${cmd} status`);
    assert.deepStrictEqual(
      parseModeChange(`${cmd} please`, defaultCSTMAN),
      { action: 'set', mode: MODE_OF[cmd] },
      `${cmd} please`
    );
  }
});

test('/ultracave-like prefixes are not the command', () => {
  assert.strictEqual(parseModeChange('/ultracstman', defaultCSTMAN), null);
  assert.strictEqual(parseModeChange('/megacave-stats', defaultCSTMAN), null);
});

test('bare /cstman activates at the configured default', () => {
  assert.deepStrictEqual(parseModeChange('/cstman', defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

test('bare /cstman with an off default clears instead of setting mode "off"', () => {
  assert.deepStrictEqual(parseModeChange('/cstman', defaultOff), { action: 'clear' });
});

test('/cstman off|stop|disable all clear', () => {
  assert.deepStrictEqual(parseModeChange('/cstman off', defaultCSTMAN), { action: 'clear' });
  assert.deepStrictEqual(parseModeChange('/cstman stop', defaultCSTMAN), { action: 'clear' });
  assert.deepStrictEqual(parseModeChange('/cstman disable', defaultCSTMAN), { action: 'clear' });
});

// A bogus level is now REPORTED rather than swallowed (#838), but the original
// danger these two guard against is unchanged: it must never activate the
// default. 'unresolved' carries no mode, and applyModeChange/the tracker act
// only on 'set'/'clear'.
test('bogus level is unresolved — never falls through to the default', () => {
  const verdict = parseModeChange('/cstman not-a-real-level', defaultCSTMAN);
  assert.deepStrictEqual(verdict, { action: 'unresolved' });
  assert.strictEqual(verdict.mode, undefined, 'must not carry a mode');
});

test('independent modes are not reachable via /cstman <arg>', () => {
  const verdict = parseModeChange('/cstman commit', defaultCSTMAN);
  assert.strictEqual(verdict.action, 'unresolved');
  assert.strictEqual(verdict.mode, undefined, 'must not activate the mode');
});

// #838: punctuation glued to the level matched no mode, left the level
// untouched, and said nothing. Only parts[1] is read, so trailing WORDS were
// already harmless — it is the glued character that broke it.
test('punctuation glued to the level still resolves (#838)', () => {
  for (const prompt of ['/cstman ultra;', '/cstman ultra.', '/cstman ultra!', '/cstman ultra,']) {
    assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'set', mode: 'ultracave' }, prompt);
  }
});

test('punctuation glued to a hyphenated level still resolves (#838)', () => {
  assert.deepStrictEqual(
    parseModeChange('/cstman wenyan-ultra.', defaultCSTMAN),
    { action: 'set', mode: 'megacave' }
  );
  assert.deepStrictEqual(
    parseModeChange('/cstman wenyan-full,', defaultCSTMAN),
    { action: 'set', mode: 'megacave' }
  );
});

test('punctuation glued to off still deactivates (#838)', () => {
  assert.deepStrictEqual(parseModeChange('/cstman off.', defaultCSTMAN), { action: 'clear' });
});

test('trailing words after the level remain harmless', () => {
  assert.deepStrictEqual(
    parseModeChange('/cstman ultra; still too verbose', defaultCSTMAN),
    { action: 'set', mode: 'ultracave' }
  );
});

// `/cstman ?` is plausibly someone asking for help. Bare `/cstman` still
// activates; an argument that was PRESENT but normalized away must not.
test('a punctuation-only argument does not activate', () => {
  assert.deepStrictEqual(parseModeChange('/cstman ?', defaultCSTMAN), { action: 'unresolved' });
  assert.deepStrictEqual(parseModeChange('/cstman', defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

test('/cstman-commit, /cstman-review, /cstman-compress set independent modes', () => {
  assert.deepStrictEqual(parseModeChange('/cstman-commit', defaultCSTMAN), { action: 'set', mode: 'commit' });
  assert.deepStrictEqual(parseModeChange('/cstman-review', defaultCSTMAN), { action: 'set', mode: 'review' });
  assert.deepStrictEqual(parseModeChange('/cstman-compress', defaultCSTMAN), { action: 'set', mode: 'compress' });
});

test('namespaced /cstman:cstman-* variants are recognized', () => {
  assert.deepStrictEqual(parseModeChange('/cstman:cstman-commit', defaultCSTMAN), { action: 'set', mode: 'commit' });
  assert.deepStrictEqual(parseModeChange('/cstman:cstman-review', defaultCSTMAN), { action: 'set', mode: 'review' });
  assert.deepStrictEqual(parseModeChange('/cstman:cstman', defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

test('natural-language activation', () => {
  assert.deepStrictEqual(parseModeChange('activate cstman', defaultCSTMAN), { action: 'set', mode: 'cstman' });
  assert.deepStrictEqual(parseModeChange('talk like a cstman', defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

test('brevity triggers activate', () => {
  assert.deepStrictEqual(parseModeChange('be brief', defaultCSTMAN), { action: 'set', mode: 'cstman' });
  assert.deepStrictEqual(parseModeChange('fewer tokens please', defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

test('scoped brevity ("be brief in the summary") does not activate', () => {
  assert.strictEqual(parseModeChange('be brief in the summary section', defaultCSTMAN), null);
});

test('questions about cstman do not activate', () => {
  assert.strictEqual(parseModeChange('what is cstman mode?', defaultCSTMAN), null);
});

// #187: the gap between the activation verb and "cstman" was any 40
// characters, so ordinary prose that merely mentioned cstman downstream of a
// common verb switched the mode on. The gap is a whitelist of determiners and
// particles now.
test('prose with a verb and a downstream "cstman" does not activate (#187)', () => {
  for (const prompt of [
    'i want to start building a cstman-themed game',
    'help me start a cstman fire for the demo scene',
    'we should use the sprite sheet from the cstman assets folder',
    'switch to the branch that renames the cstman skill directory',
  ]) {
    assert.strictEqual(parseModeChange(prompt, defaultCSTMAN), null, prompt);
  }
});

test('real activation phrasings still activate (positive control, #187)', () => {
  for (const prompt of [
    'activate cstman',
    'activate cstman mode',
    'enable the cstman mode',
    'turn on cstman',
    'turn on the cstman mode please',
    'switch to cstman',
    'i want cstman mode',
    'give me cstman',
    'please use cstman now',
    'talk like cstman',
    'talk like a cstman',
  ]) {
    assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'set', mode: 'cstman' }, prompt);
  }
});

// #187: "don't activate cstman" activated. The guard is activation-only —
// see the asymmetry note in cstman-parse.js and the #838 test below, which
// keeps "don't stop cstman" deactivating on purpose.
test('a negated activation does not activate (#187)', () => {
  for (const prompt of [
    "don't activate cstman",
    'do not turn on cstman',
    'never enable cstman mode',
    "i don't want cstman for this file",
    "please don't talk like a cstman",
    'no need to use cstman here',
  ]) {
    assert.strictEqual(parseModeChange(prompt, defaultCSTMAN), null, prompt);
  }
});

// The negator does not always sit next to the verb it negates: "don't want you
// to use cstman" negates `want`, while the trigger that actually matches is
// the `use` in the complement clause. Scoping the guard to the clause rather
// than to a fixed word window is what catches these.
test('a negated activation with a complement clause does not activate (#187)', () => {
  for (const prompt of [
    "i don't want you to use cstman",
    "don't ask me to enable cstman",
    "please don't switch me to cstman",
    "i don't need you to talk like a cstman",
    'never ask me to turn on cstman mode',
  ]) {
    assert.strictEqual(parseModeChange(prompt, defaultCSTMAN), null, prompt);
  }
});

// The other half of clause scoping: a negation must not swallow a LATER,
// independent positive command. Widening the guard to "a negator appears
// anywhere earlier in the prompt" would break exactly these.
test('a negated clause does not suppress a later activation (#187)', () => {
  for (const prompt of [
    "don't use vim, activate cstman",
    "i don't like verbose output. activate cstman",
    "never mind the linter — turn on cstman",
  ]) {
    assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'set', mode: 'cstman' }, prompt);
  }
});

test('natural-language deactivation', () => {
  assert.deepStrictEqual(parseModeChange('turn cstman mode off', defaultCSTMAN), { action: 'clear' });
  assert.deepStrictEqual(parseModeChange('normal mode', defaultCSTMAN), { action: 'clear' });
});

// "go back to normal mode" and "go to normal mode" are ordinary switch-back
// phrasings, but the verb alternation listed "go" and "back to" as separate,
// mutually exclusive prefixes, so "go back to" matched nothing and "go to" had
// no alternative at all. Both deactivations were silently dropped, leaving the
// user in the mode with no feedback.
test('"go back to normal mode" / "go to normal mode" deactivate like the other switch-back phrasings', () => {
  for (const prompt of [
    'go back to normal mode',
    'go to normal mode',
    'please go back to normal mode',
    'go back to normal mode and summarize the diff',
  ]) {
    assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'clear' }, prompt);
  }
});

test('vim "normal mode" (no cstman context) does not deactivate', () => {
  assert.strictEqual(parseModeChange('how do I exit vim normal mode', defaultCSTMAN), null);
});

test('INDEPENDENT_MODES is exported and matches the known set', () => {
  assert.deepStrictEqual([...INDEPENDENT_MODES].sort(), ['commit', 'compress', 'review']);
});

// ---------- skipNaturalLanguage (foreign command envelopes, #537) ----------

test('skipNaturalLanguage suppresses activation/deactivation matching entirely', () => {
  assert.strictEqual(
    parseModeChange('please activate cstman mode now', { ...defaultCSTMAN, skipNaturalLanguage: true }),
    null
  );
  assert.strictEqual(
    parseModeChange('stop cstman', { ...defaultCSTMAN, skipNaturalLanguage: true }),
    null
  );
});

test('skipNaturalLanguage still lets literal slash commands through', () => {
  assert.deepStrictEqual(
    parseModeChange('/cstman ultra', { ...defaultCSTMAN, skipNaturalLanguage: true }),
    { action: 'set', mode: 'ultracave' }
  );
});

// ---------- unwrapQuotes (opencode `run` path) ----------

test('unwrapQuotes strips a symmetric quote wrapper before matching', () => {
  assert.deepStrictEqual(
    parseModeChange('"/cstman lite"', { ...defaultCSTMAN, unwrapQuotes: true }),
    { action: 'set', mode: 'cstman' }
  );
});

test('without unwrapQuotes, a quoted command does not match', () => {
  assert.strictEqual(parseModeChange('"/cstman lite"', defaultCSTMAN), null);
});

// ---------- expandedTpl (opencode's expanded command-template bodies) ----------

test('expandedTpl recognizes the ultracave and megacave templates', () => {
  const read = (name) => fs.readFileSync(
    path.join(__dirname, '..', 'src', 'plugins', 'opencode', 'commands', name), 'utf8',
  ).replace(/^---[\s\S]*?---\s*/, '');
  assert.deepStrictEqual(
    parseModeChange(read('ultracave.md'), { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'ultracave' }
  );
  assert.deepStrictEqual(
    parseModeChange(read('megacave.md'), { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'megacave' }
  );
  assert.deepStrictEqual(
    parseModeChange(read('cstman.md').replace('$ARGUMENTS', ''), { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'cstman' }
  );
});

test('expandedTpl recognizes the generic "/cstman <arg>" template', () => {
  assert.deepStrictEqual(
    parseModeChange('Activate cstman mode: ultra', { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'ultracave' }
  );
});

test('expandedTpl: empty level (bare "/cstman", multi-line template head) uses the default', () => {
  // The real commands/cstman.md template puts `Activate cstman mode:
  // $ARGUMENTS` on its own line, followed by a blank line and then fixed
  // boilerplate ("If no argument given, use cstman. If \"off\", deactivate.").
  // With $ARGUMENTS empty, whitespace-collapse used to merge that boilerplate
  // directly onto the same line as the (empty) argument, so the word "if"
  // (from "If no level given ...") was captured as the level and rejected as
  // bogus — a bare `/cstman` in opencode silently never activated.
  // Regression guard for that (matches the shape exercised by
  // tests/installer/opencode.test.mjs's real-hooks test).
  const templateNoArgs =
    'Activate cstman mode: \n\n' +
    'If no argument given, use cstman. If "off", deactivate.';
  assert.deepStrictEqual(
    parseModeChange(templateNoArgs, { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'cstman' }
  );
});

test('expandedTpl: bogus level in the template is unresolved, not the default (#602 drift)', () => {
  assert.deepStrictEqual(
    parseModeChange('Activate cstman mode: not-a-real-level', { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'unresolved' }
  );
});

test('expandedTpl recognizes the independent-mode command templates (#602 drift)', () => {
  assert.deepStrictEqual(
    parseModeChange('Generate a commit message for the current staged changes.', { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'commit' }
  );
  assert.deepStrictEqual(
    parseModeChange('Review the current diff (or files: ).', { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'review' }
  );
  assert.deepStrictEqual(
    parseModeChange('Compress the file at: notes.md', { ...defaultCSTMAN, expandedTpl: true }),
    { action: 'set', mode: 'compress' }
  );
});

test('expandedTpl: no non-activation opencode template switches a prose mode', () => {
  // Every shipped command file, expanded the way opencode delivers it: front
  // matter stripped, $ARGUMENTS empty. /cstman-help listed "Activate cstman"
  // in its table, which flipped ultracave back to cstman (or turned it on).
  const dir = path.join(__dirname, '..', 'src', 'plugins', 'opencode', 'commands');
  const PROSE = new Set(['cstman', 'ultracave', 'megacave']);
  const checked = [];
  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.md'))) {
    if (PROSE.has(file.replace(/\.md$/, ''))) continue; // activation templates by design
    const body = fs.readFileSync(path.join(dir, file), 'utf8')
      .replace(/^---[\s\S]*?---\s*/, '').split('$ARGUMENTS').join('');
    for (const getDefaultMode of [() => 'cstman', () => 'ultracave']) {
      const verdict = parseModeChange(body, { getDefaultMode, expandedTpl: true, unwrapQuotes: true });
      const switches = verdict && (verdict.action === 'clear' || (verdict.action === 'set' && PROSE.has(verdict.mode)));
      assert.ok(!switches, `${file} → ${JSON.stringify(verdict)}`);
    }
    checked.push(file);
  }
  for (const f of ['cstman-help.md', 'cstman-commit.md', 'cstman-review.md', 'cstman-compress.md', 'cstman-stats.md']) {
    assert.ok(checked.includes(f), `${f} not checked`);
  }
});

test('expandedTpl: the help card opener short-circuits even a trigger in its body', () => {
  assert.strictEqual(
    parseModeChange('Show the cstman quick-reference card.\n\n| /cstman | Activate cstman |\nstop cstman', {
      ...defaultCSTMAN, expandedTpl: true,
    }),
    null
  );
});

test('without expandedTpl, template bodies are inert plain text', () => {
  assert.strictEqual(
    parseModeChange('Generate a commit message for the current staged changes.', defaultCSTMAN),
    null
  );
});

// ---------- parity with the real tracker hook ----------
// The tracker collapses whitespace/case and applies the same option set this
// module expects (getDefaultMode, skipNaturalLanguage). For a representative
// set of raw prompts, verify the flag-file outcome the tracker produces
// matches what parseModeChange's verdict implies — proving the two stay in
// sync rather than just "both look right in isolation".

function runTracker(prompt, presetFlag) {
  const cfg = fs.mkdtempSync(path.join(os.tmpdir(), 'cstman-parse-parity-'));
  try {
    if (presetFlag) fs.writeFileSync(path.join(cfg, '.cstman-active'), presetFlag);
    spawnSync(process.execPath, [HOOK_PATH], {
      input: JSON.stringify({ prompt }),
      env: { ...process.env, CLAUDE_CONFIG_DIR: cfg },
      stdio: ['pipe', 'pipe', 'pipe'],
      encoding: 'utf8',
    });
    const flagPath = path.join(cfg, '.cstman-active');
    return fs.existsSync(flagPath) ? fs.readFileSync(flagPath, 'utf8') : null;
  } finally {
    fs.rmSync(cfg, { recursive: true, force: true });
  }
}

// #838: natural-language triggers ran over the whole prompt, so any pasted
// text that merely QUOTED them fired them.
test('prose quoting "stop cstman" no longer deactivates (#838)', () => {
  const prompt = 'why does the help card say "stop cstman" or "normal mode" here?';
  assert.strictEqual(parseModeChange(prompt, defaultCSTMAN), null);
});

test('prose quoting "activate cstman" no longer activates (#838)', () => {
  assert.strictEqual(
    parseModeChange('the readme says you can "activate cstman" by typing it', defaultCSTMAN),
    null
  );
});

test('backtick-quoted triggers are inert too', () => {
  assert.strictEqual(parseModeChange('the `stop cstman` phrase is documented', defaultCSTMAN), null);
});

// The cap that was tried first broke exactly these: a user explaining WHY they
// want the mode off writes more words, not fewer, and a dropped deactivation
// is silent — the user cannot escape and is told nothing.
test('long compound deactivation still works — no length cap (#838)', () => {
  for (const prompt of [
    'that is enough compression for now — please turn off cstman mode and go back to full sentences for the rest of this task',
    'ok this is getting hard to read, stop cstman mode and then go through the auth middleware and explain the token expiry check',
  ]) {
    assert.ok(prompt.length > 120, 'fixture must be long enough to matter');
    assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'clear' }, prompt);
  }
});

test('long compound activation still works', () => {
  const prompt = 'activate cstman mode and then start by reading the proxy package and summarising how the dial guard is wired up';
  assert.ok(prompt.length > 110);
  assert.deepStrictEqual(parseModeChange(prompt, defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

test('apostrophes do not blank the command ("don\'t stop cstman, it\'s useful")', () => {
  assert.deepStrictEqual(
    parseModeChange("don't stop cstman, it's useful", defaultCSTMAN),
    { action: 'clear' }
  );
});

test('short natural-language triggers still work (positive control)', () => {
  assert.deepStrictEqual(parseModeChange('stop cstman', defaultCSTMAN), { action: 'clear' });
  assert.deepStrictEqual(parseModeChange('back to normal mode please', defaultCSTMAN), { action: 'clear' });
  assert.deepStrictEqual(parseModeChange('activate cstman', defaultCSTMAN), { action: 'set', mode: 'cstman' });
});

// A foreign slash command's own text must not toggle our mode — symmetric with
// the skipNaturalLanguage that a foreign command ENVELOPE already sets.
test('a slash-initiated prompt does not fire natural-language triggers', () => {
  assert.strictEqual(parseModeChange('/cstman-help stop cstman', defaultCSTMAN), null);
  assert.strictEqual(parseModeChange('/some-other-command activate cstman', defaultCSTMAN), null);
});

test('slash commands themselves are unaffected by prompt length', () => {
  const long = '/cstman ultra ' + 'x'.repeat(400);
  assert.deepStrictEqual(parseModeChange(long, defaultCSTMAN), { action: 'set', mode: 'ultracave' });
});

// An independent mode IS a real mode, just not reachable this way — saying
// "not recognized" would deny a mode the user can see in the docs.
test('an independent mode via /cstman <arg> reports its own command', () => {
  assert.deepStrictEqual(
    parseModeChange('/cstman commit', defaultCSTMAN),
    { action: 'unresolved', independentMode: 'commit' }
  );
});

test('a quoted level resolves (leading punctuation stripped too)', () => {
  assert.deepStrictEqual(parseModeChange('/cstman "ultra"', defaultCSTMAN), { action: 'set', mode: 'ultracave' });
});

const parityCases = [
  { prompt: '/cstman ultra', preset: null },
  { prompt: '/ultracave', preset: 'cstman' },
  { prompt: '/cstman off', preset: 'cstman' },
  { prompt: '/cstman not-a-real-level', preset: 'ultracave' },
  { prompt: 'be brief', preset: null },
  { prompt: 'activate cstman', preset: null },
  { prompt: 'stop cstman', preset: 'cstman' },
  { prompt: 'what is cstman mode?', preset: null },
];

for (const { prompt, preset } of parityCases) {
  test(`parity: "${prompt}" (preset=${preset}) matches shared-parser verdict`, () => {
    const normalized = prompt.trim().toLowerCase().replace(/\s+/g, ' ');
    const verdict = parseModeChange(normalized, { getDefaultMode: () => 'cstman' });
    // null and 'unresolved' both mean "leave the flag exactly as it was".
    const expected =
      verdict === null ? (preset || null) :
      verdict.action === 'unresolved' ? (preset || null) :
      verdict.action === 'clear' ? null :
      verdict.mode;
    assert.strictEqual(runTracker(prompt, preset), expected);
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
