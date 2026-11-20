"""Tests for cstman-mode-tracker.js prompt parsing (issues #598, #599, #856).

Drives the UserPromptSubmit hook with real prompts over stdin against an
isolated CLAUDE_CONFIG_DIR and asserts the flag-file state afterwards.

#598: natural-language triggers misfired — "turn cstman mode off"
ACTIVATED cstman (and clobbered the level to default), "turn cstman off"
was a no-op, questions about cstman armed it, and vim's "normal mode"
deactivated it.

#599: one-shot independent modes (/cstman-commit etc.) permanently
overwrote the active prose level, and the plugin-namespaced
/cstman:cstman-commit|-review variants were not recognized at all.
"""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKER = REPO_ROOT / "src" / "hooks" / "cstman-mode-tracker.js"


class ModeTrackerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cstman-tracker-")
        self.claude_dir = Path(self._tmp.name) / ".claude"
        self.claude_dir.mkdir(parents=True)
        self.flag = self.claude_dir / ".cstman-active"
        self.prev = self.claude_dir / ".cstman-active.prev"

    def tearDown(self):
        self._tmp.cleanup()

    def send(self, prompt):
        env = os.environ.copy()
        env.pop("CSTMAN_DEFAULT_MODE", None)
        env["HOME"] = self._tmp.name
        env["USERPROFILE"] = self._tmp.name
        env["CLAUDE_CONFIG_DIR"] = str(self.claude_dir)
        return subprocess.run(
            ["node", str(TRACKER)],
            cwd=REPO_ROOT,
            env=env,
            input=json.dumps({"prompt": prompt}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

    def flag_value(self):
        return self.flag.read_text(encoding="utf-8") if self.flag.exists() else None

    # ── hook budget: act on the first complete payload, not on EOF ──────

    def test_acts_on_first_complete_payload_without_waiting_for_eof(self):
        """The hook is registered with a 5s host budget. Blocking until stdin
        EOF spends that budget waiting for a close it already has all the data
        for — the Windows pipe implementation can lag that close arbitrarily
        (#729/#833). Write one complete object, hold the pipe open, and the
        flag must land anyway."""
        env = os.environ.copy()
        env.pop("CSTMAN_DEFAULT_MODE", None)
        env["HOME"] = self._tmp.name
        env["USERPROFILE"] = self._tmp.name
        env["CLAUDE_CONFIG_DIR"] = str(self.claude_dir)

        proc = subprocess.Popen(
            ["node", str(TRACKER)],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            proc.stdin.write(json.dumps({"prompt": "/cstman ultra"}))
            proc.stdin.flush()  # deliberately NOT closed
            deadline = time.time() + 5
            while time.time() < deadline and self.flag_value() is None:
                time.sleep(0.05)
            self.assertEqual(self.flag_value(), "ultracst")
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.kill()
            proc.wait(timeout=5)

    # ── #598: deactivation word orders ──────────────────────────────────

    def test_turn_cstman_mode_off_deactivates(self):
        # Pre-fix: this ACTIVATED cstman and downgraded the mode to the default.
        self.flag.write_text("ultra", encoding="utf-8")
        self.send("turn cstman mode off")
        self.assertIsNone(self.flag_value())

    def test_turn_cstman_off_deactivates(self):
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("turn cstman off")
        self.assertIsNone(self.flag_value())

    def test_turn_off_cstman_deactivates(self):
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("turn off cstman")
        self.assertIsNone(self.flag_value())

    def test_stop_cstman_multiline_deactivates(self):
        # Pre-fix: `.*` without the s flag never matched across lines.
        self.flag.write_text("ultra", encoding="utf-8")
        self.send("stop\ncstman")
        self.assertIsNone(self.flag_value())

    def test_normal_mode_command_deactivates(self):
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("normal mode")
        self.assertIsNone(self.flag_value())

    def test_back_to_normal_mode_deactivates(self):
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("back to normal mode please")
        self.assertIsNone(self.flag_value())

    def test_vim_normal_mode_does_not_deactivate(self):
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("how do I exit vim normal mode")
        self.assertEqual(self.flag_value(), "cstman")

    # ── #598: activation guards ─────────────────────────────────────────

    def test_enable_cstman_with_stop_elsewhere_activates(self):
        # Pre-fix: "stop" anywhere suppressed activation, then the
        # deactivation regex matched "cstman and stop" and deleted the flag.
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("enable cstman and stop apologizing")
        self.assertEqual(self.flag_value(), "cstman")

    def test_question_does_not_activate(self):
        self.send("what is cstman mode?")
        self.assertIsNone(self.flag_value())
        self.send("does cstman lite mode drop articles?")
        self.assertIsNone(self.flag_value())

    def test_scoped_brevity_does_not_activate(self):
        self.send("be brief in the summary section")
        self.assertIsNone(self.flag_value())

    def test_unscoped_brevity_activates(self):
        self.send("be brief")
        self.assertEqual(self.flag_value(), "cstman")

    def test_activate_cstman_still_works(self):
        self.send("activate cstman")
        self.assertEqual(self.flag_value(), "cstman")

    def test_turn_on_cstman_mode_still_works(self):
        self.send("turn on cstman mode")
        self.assertEqual(self.flag_value(), "cstman")

    def test_talk_like_cstman_still_works(self):
        self.send("talk like a cstman")
        self.assertEqual(self.flag_value(), "cstman")

    def test_bare_cstman_mode_still_works(self):
        self.send("cstman mode")
        self.assertEqual(self.flag_value(), "cstman")

    # ── slash commands ──────────────────────────────────────────────────

    def test_slash_mode_commands(self):
        for prompt, mode in [
            ("/ultracst", "ultracst"), ("/cstman:megacst", "megacst"),
            ("/cstman ultra", "ultracst"), ("/cstman wenyan-lite", "megacst"),
            ("/cstman lite", "cstman"), ("/cstman", "cstman"),
        ]:
            with self.subTest(prompt=prompt):
                self.send(prompt)
                self.assertEqual(self.flag_value(), mode)

    def test_slash_cstman_off(self):
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("/cstman off")
        self.assertIsNone(self.flag_value())

    # ── #856: read-only mode status ──────────────────────────────────────

    def test_status_reports_active_mode_without_mutating_state(self):
        self.flag.write_text("ultracst", encoding="utf-8")
        before = self.flag.read_text(encoding="utf-8")

        result = self.send("/cstman status")

        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: ultracst",
        )
        self.assertEqual(self.flag_value(), before)
        self.assertFalse(
            (self.claude_dir / ".cstman-mode-log.jsonl").exists(),
            "status must not record a mode transition",
        )

    def test_namespaced_status_reports_the_new_id_for_a_legacy_value(self):
        self.flag.write_text("wenyan", encoding="utf-8")

        result = self.send("/cstman:cstman status")

        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: megacst",
        )
        self.assertEqual(self.flag_value(), "wenyan", "status must not rewrite the file")

    def test_status_reports_independent_modes(self):
        for mode in ("commit", "review", "compress"):
            with self.subTest(mode=mode):
                self.flag.write_text(mode, encoding="utf-8")
                result = self.send("/cstman status")
                payload = json.loads(result.stdout)
                self.assertEqual(
                    payload["hookSpecificOutput"]["additionalContext"],
                    "Report this status verbatim without changing mode: CSTMAN mode: " + mode,
                )
                self.assertEqual(self.flag_value(), mode)

    def test_enveloped_status_is_read_only(self):
        self.flag.write_text("cstman", encoding="utf-8")

        result = self.send('<command-name>/cstman:cstman</command-name><command-args>status</command-args>')

        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: cstman",
        )
        self.assertEqual(self.flag_value(), "cstman")

    def test_status_reports_off_for_missing_and_durable_off_state(self):
        missing = json.loads(self.send("/cstman status").stdout)
        self.assertEqual(
            missing["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: off",
        )

        self.flag.write_text("off", encoding="utf-8")
        durable_off = json.loads(self.send("/cstman status").stdout)
        self.assertEqual(
            durable_off["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: off",
        )
        self.assertEqual(self.flag_value(), "off")

    def test_status_does_not_consume_one_shot_restore(self):
        self.flag.write_text("ultra", encoding="utf-8")
        self.send("/cstman-commit")
        prev = self.prev.read_text(encoding="utf-8")

        result = self.send("/cstman status")

        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: commit",
        )
        self.assertEqual(self.flag_value(), "commit")
        self.assertEqual(self.prev.read_text(encoding="utf-8"), prev)

    def test_status_rejects_untrusted_flag_contents(self):
        outside = self.claude_dir / 'outside'
        outside.write_text('ultra', encoding='utf-8')
        self.flag.symlink_to(outside)
        self.assertNotIn('mode: ultra', self.send('/cstman status').stdout)
        self.assertEqual(outside.read_text(encoding="utf-8"), 'ultra')
        self.flag.unlink()
        self.flag.write_text('injected instructions', encoding='utf-8')
        result = self.send('/cstman status')
        self.assertIn('CSTMAN mode: off', result.stdout)
        self.assertNotIn('injected instructions', result.stdout)
        self.assertEqual(self.flag.read_text(encoding="utf-8"), 'injected instructions')

    # ── #599: one-shot independent modes ────────────────────────────────

    def test_commit_restores_prior_mode_on_next_prompt(self):
        # A legacy 'ultra' flag comes back as its new id.
        self.flag.write_text("ultra", encoding="utf-8")
        self.send("/cstman-commit")
        self.assertEqual(self.flag_value(), "commit")
        r = self.send("ordinary follow-up question")
        self.assertEqual(self.flag_value(), "ultracst")
        self.assertIn("CSTMAN MODE ACTIVE (ultracst)", r.stdout)

    def test_commit_with_no_prior_mode_deactivates_after(self):
        self.send("/cstman-commit")
        self.assertEqual(self.flag_value(), "commit")
        r = self.send("ordinary follow-up question")
        self.assertIsNone(self.flag_value())
        self.assertNotIn("CSTMAN MODE ACTIVE", r.stdout)

    def test_chained_independent_modes_keep_original_prev(self):
        self.flag.write_text("wenyan-ultra", encoding="utf-8")
        self.send("/cstman-commit")
        self.send("/cstman-review")
        self.assertEqual(self.flag_value(), "review")
        self.send("ordinary follow-up question")
        self.assertEqual(self.flag_value(), "megacst")

    def test_namespaced_commit_and_review_recognized(self):
        # Pre-fix: only compress and stats had the /cstman:cstman- variant.
        self.flag.write_text("cstman", encoding="utf-8")
        self.send("/cstman:cstman-commit")
        self.assertEqual(self.flag_value(), "commit")
        self.send("next prompt")  # restore
        self.send("/cstman:cstman-review")
        self.assertEqual(self.flag_value(), "review")

    def test_no_reinforcement_during_independent_turn(self):
        self.flag.write_text("cstman", encoding="utf-8")
        r = self.send("/cstman-commit")
        self.assertNotIn("CSTMAN MODE ACTIVE", r.stdout)

    def test_deactivation_clears_saved_prev(self):
        self.flag.write_text("ultra", encoding="utf-8")
        self.send("/cstman-commit")
        self.send("stop cstman")
        self.assertIsNone(self.flag_value())
        self.assertFalse(self.prev.exists(), "prev file must not survive deactivation")
        self.send("ordinary prompt")
        self.assertIsNone(self.flag_value(), "nothing should resurrect the mode")


class SessionScopedModeTests(unittest.TestCase):
    """Per-session state: two Claude Code windows must not share a mode.

    Everything here drives the same hook, but with a session_id in the payload
    — the field Claude Code actually sends and the tests above deliberately
    omit, so those keep exercising the legacy machine-wide fallback.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="cstman-session-")
        self.claude_dir = Path(self._tmp.name) / ".claude"
        self.claude_dir.mkdir(parents=True)
        self.legacy = self.claude_dir / ".cstman-active"
        self.sessions = self.claude_dir / ".cstman-sessions"

    def tearDown(self):
        self._tmp.cleanup()

    def send(self, prompt, session_id):
        env = os.environ.copy()
        env.pop("CSTMAN_DEFAULT_MODE", None)
        env["HOME"] = self._tmp.name
        env["USERPROFILE"] = self._tmp.name
        env["CLAUDE_CONFIG_DIR"] = str(self.claude_dir)
        return subprocess.run(
            ["node", str(TRACKER)],
            cwd=REPO_ROOT,
            env=env,
            input=json.dumps({"prompt": prompt, "session_id": session_id}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

    def mode_of(self, session_id):
        p = self.sessions / f"{session_id}.mode"
        return p.read_text(encoding="utf-8") if p.exists() else None

    def legacy_value(self):
        return self.legacy.read_text(encoding="utf-8") if self.legacy.exists() else None

    def test_parallel_sessions_keep_separate_modes(self):
        self.send("/ultracst", "sessA")
        self.send("/megacst", "sessB")
        self.assertEqual(self.mode_of("sessA"), "ultracst")
        self.assertEqual(self.mode_of("sessB"), "megacst")

    def test_status_uses_session_mode_before_legacy_fallback(self):
        self.send("/ultracst", "sessA")
        self.send("/megacst", "sessB")

        status_a = json.loads(self.send("/cstman status", "sessA").stdout)
        status_b = json.loads(self.send("/cstman status", "sessB").stdout)

        self.assertEqual(
            status_a["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: ultracst",
        )
        self.assertEqual(
            status_b["hookSpecificOutput"]["additionalContext"],
            "Report this status verbatim without changing mode: CSTMAN mode: megacst",
        )

    def test_status_preserves_session_off_and_all_state_bytes(self):
        self.send('/cstman off', 'sessA')
        self.send('/cstman ultra', 'sessB')
        self.send('/cstman-commit', 'sessB')
        def snapshot():
            return {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in self.claude_dir.rglob('*') if p.is_file()}
        before = snapshot()
        for session, expected in [('sessA', 'off'), ('sessB', 'commit'), ('../invalid', 'commit')]:
            response = self.send('/cstman status', session)
            self.assertIn('CSTMAN mode: ' + expected, response.stdout)
            self.assertEqual(snapshot(), before)
        self.send('continue', 'sessB')
        self.assertEqual(self.mode_of('sessB'), 'ultracst')

    def test_reinforcement_reflects_own_session(self):
        self.send("/ultracst", "sessA")
        self.send("/megacst", "sessB")
        r = self.send("ordinary prompt", "sessA")
        self.assertIn("CSTMAN MODE ACTIVE (ultracst)", r.stdout)
        self.assertNotIn("megacst", r.stdout)

    def test_deactivating_one_session_leaves_the_other_active(self):
        self.send("/ultracst", "sessA")
        self.send("/cstman", "sessB")
        self.send("stop cstman", "sessB")

        self.assertEqual(self.mode_of("sessB"), "off", "off must be durable on disk")
        r = self.send("ordinary prompt", "sessB")
        self.assertNotIn("CSTMAN MODE ACTIVE", r.stdout)

        r = self.send("ordinary prompt", "sessA")
        self.assertIn("CSTMAN MODE ACTIVE (ultracst)", r.stdout)

    def test_legacy_mirror_never_holds_literal_off(self):
        # An older statusline or hook reading the legacy path must see absence,
        # not the string 'off' — it would render [CSTMAN:OFF] / inject
        # "CSTMAN MODE ACTIVE (off)".
        self.send("/cstman", "sessA")
        self.assertEqual(self.legacy_value(), "cstman")
        self.send("stop cstman", "sessA")
        self.assertIsNone(self.legacy_value())

    def test_legacy_mirror_tracks_last_write(self):
        self.send("/ultracst", "sessA")
        self.send("/megacst", "sessB")
        self.assertEqual(self.legacy_value(), "megacst")

    def test_prev_restore_is_session_scoped(self):
        # Each window runs a one-shot skill; each must return to its own mode.
        self.send("/ultracst", "sessA")
        self.send("/megacst", "sessB")
        self.send("/cstman-commit", "sessA")
        self.send("/cstman-commit", "sessB")

        self.send("follow-up", "sessA")
        self.assertEqual(self.mode_of("sessA"), "ultracst")
        self.send("follow-up", "sessB")
        self.assertEqual(self.mode_of("sessB"), "megacst")

    def test_malformed_session_id_falls_back_to_legacy(self):
        self.send("/ultracst", "../../escape")
        self.assertEqual(self.legacy_value(), "ultracst", "must degrade, not fail")
        self.assertFalse(
            self.sessions.exists() and any(self.sessions.iterdir()),
            "no state file may be created for a rejected session id",
        )

    def test_session_id_cannot_escape_the_sessions_directory(self):
        for bad in ["../../evil", "a/b", "..", "x" * 200]:
            self.send("/ultracst", bad)
        stray = list(self.claude_dir.rglob("*evil*")) + list(self.claude_dir.rglob("*.mode"))
        self.assertEqual(stray, [], f"unexpected files written: {stray}")

    def test_one_shot_skill_does_not_switch_an_off_session_on(self):
        # A stale machine-wide prev from some earlier session-less run.
        (self.claude_dir / ".cstman-active.prev").write_text("ultra", encoding="utf-8")

        # This session never had cstman on, so /cstman-commit displaces
        # nothing and saves no prev. Borrowing the stale machine-wide one would
        # switch the session on at ultra when the skill's turn ended.
        self.send("/cstman-commit", "sessY")
        r = self.send("ordinary follow-up", "sessY")

        self.assertNotIn("CSTMAN MODE ACTIVE", r.stdout)
        self.assertEqual(self.mode_of("sessY"), "off")
        self.assertEqual(
            (self.claude_dir / ".cstman-active.prev").read_text(encoding="utf-8"), "ultra",
            "a session-scoped restore must not consume machine-wide state",
        )

    def test_existing_legacy_flag_is_honored_before_first_session_write(self):
        # Upgrade path: only the old flag exists when a new session starts,
        # holding a pre-three-skill level name.
        self.legacy.write_text("wenyan", encoding="utf-8")
        r = self.send("ordinary prompt", "sessA")
        self.assertIn("CSTMAN MODE ACTIVE (megacst)", r.stdout)

    def test_legacy_session_file_resolves_to_its_skill(self):
        self.sessions.mkdir(parents=True)
        (self.sessions / "sessA.mode").write_text("wenyan-lite", encoding="utf-8")
        self.legacy.write_text("lite", encoding="utf-8")
        r = self.send("ordinary prompt", "sessA")
        self.assertIn("CSTMAN MODE ACTIVE (megacst)", r.stdout)
        r = self.send("ordinary prompt", "sessNoState")
        self.assertIn("CSTMAN MODE ACTIVE (cstman)", r.stdout, "mirror 'lite' reads as cstman")


if __name__ == "__main__":
    unittest.main()
