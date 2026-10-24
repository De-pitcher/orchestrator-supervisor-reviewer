"""Regression tests for R23 (T25): audit the current accepted artifact set.

``TestCompletionFreshnessCleanControl`` is the activation baseline that already
passes: an unchanged governed snapshot diffs to nothing.

Every other class drives real ``start``/``verify``/``review``/``done``/``audit``
handlers against a throwaway project. The ``RED`` classes reproduce the defects
that exist before T25:

* ``cmd_audit`` trusts historical ``done`` flags. It never recomputes the
  governed tree, so a post-completion edit, addition or deletion of a governed
  file still audits successfully.
* Neither the task card nor ``config.json`` is re-checked at audit time, so an
  edited card or a changed configuration keeps its historical PASS.
* Evidence for a task completed under a previous approval is reused after a new
  approval, because requirement rows read the newest spec review regardless of
  whether the accepted bytes still exist.
* ``cmd_start`` silently snapshots whatever is on disk, so editing a governed
  file before starting the next task launders an unreviewed change into that
  task's baseline.
* ``cmd_verify`` only re-checks scope after the commands run. A command that
  rewrites an allowed file mid-run still verifies, so the final bytes are
  accepted although no run observed them.
* Freshness metadata is absent from ``done`` records and nothing fails closed
  when the state and the ledger disagree, or when a completion record is
  truncated or points at a foreign verification.
* There is no read-only ``audit --check``: the only audit path writes
  ``.ai/AUDIT.md``.

The ``Control`` classes must keep passing after the fix. They cover a clean
completion, ignored cache writes, two sequential overlapping tasks where the
later task legitimately supersedes the earlier bytes, edits made after ``start``,
legitimate addition/deletion/recreation of governed files, a CRLF plan approval,
legacy ledger-chain readability and an unchanged repeat audit that runs no
commands.

Run: python -m unittest discover -s tests -p test_completion_freshness.py -v
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.osr as osr


def canon_digest(manifest):
    """Canonical digest of a path-to-sha map (test-side, not a T25 symbol)."""
    canon = {path: manifest[path] for path in sorted(manifest or {})}
    return osr.sha_text(json.dumps(canon, sort_keys=True, separators=(",", ":")))


def raw_sha(path):
    """SHA-256 of a project file's raw bytes (test-side, not a T25 symbol)."""
    p = Path(path)
    if not p.is_absolute():
        p = osr.ROOT / p
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- fixtures
RUNNER = (
    "import sys\n"
    "name = sys.argv[1] if len(sys.argv) > 1 else 'test_unknown'\n"
    "sys.stdout.write('%s (proj.Suite.%s) ... ok\\n' % (name, name))\n"
    "sys.stdout.write('\\n----------------------------------------------------------------------\\n')\n"
    "sys.stdout.write('Ran 1 test in 0.001s\\n\\nOK\\n')\n"
)

MUTATING_RUNNER = (
    "import pathlib\n"
    "import sys\n"
    "name = sys.argv[1] if len(sys.argv) > 1 else 'test_unknown'\n"
    "marker = pathlib.Path('.ai/mutate-on-verify')\n"
    "if marker.exists():\n"
    "    pathlib.Path('a.py').write_text('VALUE = 999\\n', encoding='utf-8')\n"
    "sys.stdout.write('%s (proj.Suite.%s) ... ok\\n' % (name, name))\n"
    "sys.stdout.write('\\n----------------------------------------------------------------------\\n')\n"
    "sys.stdout.write('Ran 1 test in 0.001s\\n\\nOK\\n')\n"
)

PLAN_ONE = """# Plan
## Goal
Prove completion freshness for governed files.
## Non-goals
No unrelated refactors and no new dependencies.
## Requirements
- R1: alpha value
  - AC: alpha returns the accepted value [test_alpha]
  - Check: auto

## Assumptions
- [x] Python 3 only
## Open questions
"""

PLAN_TWO = """# Plan
## Goal
Prove completion freshness for governed files.
## Non-goals
No unrelated refactors and no new dependencies.
## Requirements
- R1: alpha value
  - AC: alpha returns the accepted value [test_alpha]
  - Check: auto
- R2: beta value
  - AC: beta returns the accepted value [test_beta]
  - Check: auto

## Assumptions
- [x] Python 3 only
## Open questions
"""

PLAN_THREE = """# Plan
## Goal
Prove completion freshness for governed files.
## Non-goals
No unrelated refactors and no new dependencies.
## Requirements
- R1: alpha value
  - AC: alpha returns the accepted value [test_alpha]
  - Check: auto
- R2: beta value
  - AC: beta returns the accepted value [test_beta]
  - Check: auto
- R3: gamma value
  - AC: gamma returns the accepted value [test_beta]
  - Check: auto

## Assumptions
- [x] Python 3 only
## Open questions
"""

CARD = """# {tid}: {req} implementation
id: {tid}
requirements: {req}
{depends}allowed_files: {allowed}
context_files: .ai/PLAN.md
verify: {verify}

## Goal
Implement {req} inside the declared scope.
## Constraints
Keep every change inside allowed_files.
## Do not
Change files outside allowed_files or weaken an assertion.
## Definition of done
The declared test passes and both reviews cite the accepted bytes.
"""

SPEC_TEMPLATE = 'R{num}: PASS @ a.py:1 "VALUE = {value}"\n\nVERDICT: PASS\n'

QUALITY_BODY = """C1: PASS - no imports were added to the changed module
C2: PASS - integers only, no edge cases required by the plan
C3: NA - no input handling, credentials or network access involved
C4: PASS - no stubs, TODO markers or placeholder text present
C5: PASS - no other callers exist and the module contract is unchanged
C6: PASS - the test asserts one exact value and contains no skips
C7: PASS - formatting matches the surrounding project style
C8: PASS - the delta stays inside the card's allowed_files

BREAK_ATTEMPTS:
- Call the value with a negative number and confirm the plan allows it
- Import the module twice and confirm no import side effects appear
- Replace the value with a string and observe the type is unchecked

VERDICT: PASS
"""


def quoted_python():
    return '"%s"' % sys.executable


class TestCompletionFreshnessCleanControl(unittest.TestCase):
    """Clean control fixture for T25 (R23): unchanged snapshot.

    Verifies that diff_tree produces an empty diff dict and identical
    fingerprint when comparing an unchanged tree snapshot.
    """

    def test_clean_control_unchanged_snapshot(self):
        fake_tree = {
            "file_a.py": {"sha": "1111aaaa2222bbbb", "size": 128},
            "file_b.py": {"sha": "3333cccc4444dddd", "size": 256},
        }
        diff = osr.diff_tree(fake_tree, fake_tree)
        self.assertEqual(diff, {})
        fp = osr.fingerprint(diff, fake_tree)
        self.assertEqual(fp, osr.sha_text(""))


class _FreshnessProjectCase(unittest.TestCase):
    """Drive the real handlers against a throwaway project."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = osr.ROOT
        self._old_json = osr.JSON_MODE
        osr.ROOT = Path(self._tmp.name)
        osr.JSON_MODE = False
        for name in ("tasks", "logs", "snapshots", "reviews"):
            osr.ai(name).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        osr.JSON_MODE = self._old_json
        osr.ROOT = self._old_root
        self._tmp.cleanup()

    # -- file helpers ---------------------------------------------------------
    def write(self, rel, text):
        p = osr.ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_bytes(self, rel, data):
        p = osr.ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def read(self, rel):
        return (osr.ROOT / rel).read_text(encoding="utf-8")

    def remove(self, rel):
        (osr.ROOT / rel).unlink()

    def snapshot_files(self, subdir):
        base = osr.ROOT / subdir
        out = {}
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out[p.relative_to(osr.ROOT).as_posix()] = p.read_bytes()
        return out

    def snapshot_all(self):
        """Raw bytes of every project file except VCS internals."""
        out = {}
        for p in sorted(osr.ROOT.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(osr.ROOT).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            out[rel] = p.read_bytes()
        return out

    # -- handler drivers ------------------------------------------------------
    def call(self, fn, ns):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                fn(ns)
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        return code, out.getvalue()

    def cli(self, *args):
        argv = ["osr", "--root", str(osr.ROOT)] + list(args)
        old = sys.argv
        sys.argv = argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                try:
                    osr.main()
                    code = 0
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        finally:
            sys.argv = old
        return code, out.getvalue()

    def start(self, tid):
        return self.call(osr.cmd_start, argparse.Namespace(task=tid, model="builder-model"))

    def verify(self, tid):
        return self.call(osr.cmd_verify, argparse.Namespace(task=tid))

    def review(self, tid, stage):
        return self.call(
            osr.cmd_review,
            argparse.Namespace(task=tid, stage=stage, reviewer="peer-model"),
        )

    def done(self, tid):
        return self.call(osr.cmd_done, argparse.Namespace(task=tid))

    def audit(self):
        return self.call(osr.cmd_audit, argparse.Namespace(anchor=None))

    def waive(self, tid, flag, reason):
        return self.call(
            osr.cmd_waive,
            argparse.Namespace(
                task=tid, flag=flag, flag_pos=None, reason=reason,
                approved_by=None, secret=None,
            ),
        )

    # -- project construction -------------------------------------------------
    def build(self, tasks=1, runner="plain"):
        self.write("run_checks.py", MUTATING_RUNNER if runner == "mutating" else RUNNER)
        self.write("a.py", "VALUE = 1\n")
        self.write("b.py", "OTHER = 0\n")
        plans = {1: PLAN_ONE, 2: PLAN_TWO, 3: PLAN_THREE}
        self.write(".ai/PLAN.md", plans[tasks])

        commands = {}
        for i in range(1, tasks + 1):
            tid = "T%d" % i
            req = "R%d" % i
            cmd = "%s run_checks.py test_%s" % (
                quoted_python(),
                "alpha" if i == 1 else "beta",
            )
            commands["check_" + tid.lower()] = {"cmd": cmd, "verified": True}
            self.write(
                ".ai/tasks/%s.md" % tid,
                CARD.format(
                    tid=tid,
                    req=req,
                    depends="depends_on: T1\n" if i > 1 else "",
                    allowed="a.py" if i == 1 else "a.py, b.py, c.py",
                    verify=cmd,
                ),
            )

        cfg = dict(osr.DEFAULT_CFG)
        cfg["commands"] = commands
        osr.save_cfg(cfg)
        for name, entry in commands.items():
            osr.Ledger().append(
                "cmd_confirm", name=name, cmd=entry["cmd"], ok=True, exit=0,
                run_id="seed-" + name, log="seed.log", output_sha="0" * 64,
            )
        code, out = self.call(osr.cmd_approve, argparse.Namespace(by=["human"], secret=None))
        self.assertEqual(code, 0, "fixture approval failed: %s" % out)

    def publish(self, tid, value):
        num = tid[1:]
        self.write("a.py", "VALUE = %s\n" % value)
        self.write(".ai/reviews/%s.spec.md" % tid, SPEC_TEMPLATE.format(num=num, value=value))
        self.write(".ai/reviews/%s.quality.md" % tid, QUALITY_BODY)

    def publish_change(self, tid, rel, text, evidence_line=None):
        """Write one governed change and cite it from a fresh spec review."""
        self.write(rel, text)
        line = evidence_line or text.splitlines()[0]
        self.write(
            ".ai/reviews/%s.spec.md" % tid,
            'R%s: PASS @ %s:1 "%s"\n\nVERDICT: PASS\n' % (tid[1:], rel, line),
        )
        self.write(".ai/reviews/%s.quality.md" % tid, QUALITY_BODY)

    def finish(self, tid, assert_ok=True):
        """Verify, review and close a task that was already started."""
        for label, step in (
            ("verify", lambda: self.verify(tid)),
            ("spec review", lambda: self.review(tid, "spec")),
            ("quality review", lambda: self.review(tid, "quality")),
        ):
            code, out = step()
            if assert_ok:
                self.assertEqual(code, 0, "%s %s failed: %s" % (label, tid, out))
        return self.done(tid)

    def complete(self, tid, value, assert_ok=True, started=False):
        """Start, implement, verify and review one task. Returns done output."""
        if not started:
            code, out = self.start(tid)
            if assert_ok:
                self.assertEqual(code, 0, "start %s failed: %s" % (tid, out))
        self.publish(tid, value)
        return self.finish(tid, assert_ok=assert_ok)

    def complete_ok(self, tid, value, started=False):
        code, out = self.complete(tid, value, started=started)
        self.assertEqual(code, 0, "done %s failed: %s" % (tid, out))
        return out

    def ledger_entries(self):
        return osr.Ledger().entries()

    def rewrite_ledger(self, mutate):
        """Rewrite the ledger, re-sealing the hash chain, after ``mutate(entry)``.

        Used only to simulate a tampered or interrupted historical write in the
        throwaway project. The chain stays internally valid so the audit reacts
        to the record contents rather than to a broken hash.
        """
        entries = self.ledger_entries()
        prev = osr.ZERO
        lines = []
        for entry in entries:
            body = {k: v for k, v in entry.items() if k != "hash"}
            mutate(body)
            body["prev"] = prev
            body["hash"] = osr.sha_text(prev + json.dumps(body, sort_keys=True))
            prev = body["hash"]
            lines.append(json.dumps(body))
        osr.ai("ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def last_seq(self):
        entries = self.ledger_entries()
        return entries[-1]["seq"] if entries else 0


class TestCleanCompletionControls(_FreshnessProjectCase):
    """R23 controls: legitimate completions keep auditing successfully."""

    def test_clean_single_task_completion_audits_successfully(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        code, out = self.audit()
        self.assertEqual(code, 0, "a clean completion did not audit: %s" % out)

    def test_ignored_cache_changes_do_not_invalidate_completion(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        self.write("__pycache__/a.cpython-314.pyc", "cache")
        self.write(".pytest_cache/v/cache/nodeids", "[]")
        self.write(".ai/logs/notes.txt", "scratch")
        code, out = self.audit()
        self.assertEqual(code, 0, "ignored files invalidated a clean audit: %s" % out)

    def test_sequential_overlapping_tasks_both_audit_successfully(self):
        self.build(tasks=2)
        self.complete_ok("T1", 2)
        self.complete_ok("T2", 3)
        code, out = self.audit()
        self.assertEqual(
            code, 0,
            "a later task that legitimately superseded earlier bytes was rejected: %s" % out,
        )

    def test_edits_after_start_are_reviewed_normally(self):
        self.build(tasks=2)
        self.complete_ok("T1", 2)
        code, out = self.start("T2")
        self.assertEqual(code, 0, "clean start of the next task failed: %s" % out)
        self.complete_ok("T2", 4, started=True)
        code, out = self.audit()
        self.assertEqual(code, 0, "post-start implementation was rejected: %s" % out)


class TestPostCompletionDrift(_FreshnessProjectCase):
    """RED: post-completion changes to governed content must fail the audit."""

    def test_modified_governed_file_after_completion_fails_audit(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        self.write("a.py", "VALUE = 666\n")
        code, out = self.audit()
        self.assertEqual(code, 1, "audit accepted a post-completion modification: %s" % out)
        self.assertIn("a.py", out)
        self.assertIn("stale", out.lower())

    def test_added_and_deleted_governed_files_after_completion_fail_audit(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        self.write("extra.py", "EXTRA = 1\n")
        self.remove("b.py")
        code, out = self.audit()
        self.assertEqual(code, 1, "audit accepted an added/deleted governed file: %s" % out)
        self.assertIn("extra.py", out)
        self.assertIn("b.py", out)
        lowered = out.lower()
        self.assertTrue(
            "stale" in lowered or "missing" in lowered or "added" in lowered,
            "deletion/addition reason is not actionable: %s" % out,
        )

    def test_changed_task_card_after_completion_fails_audit(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        card = self.read(".ai/tasks/T1.md")
        self.write(".ai/tasks/T1.md", card + "\nAlso change unrelated files.\n")
        code, out = self.audit()
        self.assertEqual(code, 1, "audit accepted an edited task card: %s" % out)
        self.assertIn("card", out.lower())

    def test_changed_config_after_completion_fails_audit(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        cfg = json.loads(self.read(".ai/config.json"))
        cfg["ignore"] = list(cfg["ignore"]) + ["scratch-ignore"]
        self.write(".ai/config.json", json.dumps(cfg, indent=2) + "\n")
        code, out = self.audit()
        self.assertEqual(code, 1, "audit accepted a changed configuration: %s" % out)
        self.assertIn("config", out.lower())


class TestTaskIdReuse(_FreshnessProjectCase):
    """RED: evidence from a previous approval may not verify a reused task ID."""

    def test_task_id_reuse_under_new_approval_is_stale(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        plan = self.read(".ai/PLAN.md").replace(
            "No unrelated refactors and no new dependencies.",
            "No unrelated refactors. The acceptance wording changed after T1.",
        )
        self.write(".ai/PLAN.md", plan)
        code, out = self.call(osr.cmd_approve, argparse.Namespace(by=["human"], secret=None))
        self.assertEqual(code, 0, "fixture re-approval failed: %s" % out)
        code, out = self.audit()
        self.assertEqual(
            code, 1,
            "an old completion was reused under a new approval: %s" % out,
        )
        self.assertIn("T1", out)
        lowered = out.lower()
        self.assertTrue(
            "stale" in lowered or "re-approv" in lowered or "reused" in lowered,
            "reuse reason is not actionable: %s" % out,
        )


class TestPreStartDrift(_FreshnessProjectCase):
    """RED: edits before the next start must not become that task's baseline."""

    def test_editing_governed_file_before_start_is_rejected(self):
        self.build(tasks=2)
        self.complete_ok("T1", 2)
        self.write("a.py", "VALUE = 777\n")
        code, out = self.start("T2")
        self.assertNotEqual(
            code, 0,
            "start laundered an unreviewed change into the T2 baseline: %s" % out,
        )
        self.assertIn("a.py", out)
        lowered = out.lower()
        self.assertTrue(
            "drift" in lowered or "not accepted" in lowered or "changed since" in lowered,
            "drift reason is not actionable: %s" % out,
        )


class TestMidVerificationWrites(_FreshnessProjectCase):
    """RED: bytes written while a command runs need a new stable verification."""

    def test_edit_during_verify_requires_a_stable_rerun(self):
        self.build(tasks=1, runner="mutating")
        # The ready-to-run fixture has no marker, so start sees the approved
        # bytes and runs no mutating command. The marker is created only AFTER
        # start, exactly where the pre-start guard must not be weakened.
        code, out = self.start("T1")
        self.assertEqual(code, 0, "start failed: %s" % out)
        self.write("a.py", "VALUE = 2\n")
        self.write(".ai/mutate-on-verify", "mutate during the next verify\n")
        code, out = self.verify("T1")
        self.assertNotEqual(
            code, 0,
            "verify accepted bytes that no run observed as the final tree: %s" % out,
        )
        lowered = out.lower()
        self.assertTrue(
            "changed during" in lowered or "stable" in lowered or "another run" in lowered,
            "mid-run write reason is not actionable: %s" % out,
        )
        entry = osr.Ledger().latest("verify", "T1")
        self.assertIsNotNone(entry)
        self.assertFalse(entry["data"].get("ok"), entry)
        self.assertEqual(self.read("a.py"), "VALUE = 999\n")

        # The bytes are now stable. Without the marker a rerun observes them and
        # must be accepted; the task can then be reviewed and completed.
        self.remove(".ai/mutate-on-verify")
        self.write(".ai/reviews/T1.spec.md", SPEC_TEMPLATE.format(num="1", value=999))
        self.write(".ai/reviews/T1.quality.md", QUALITY_BODY)
        code, out = self.verify("T1")
        self.assertEqual(code, 0, "a rerun on stable bytes did not verify: %s" % out)
        code, out = self.finish("T1", assert_ok=False)
        self.assertEqual(code, 0, "the stable rerun could not be completed: %s" % out)
        code, out = self.audit()
        self.assertEqual(code, 0, "a verified stable rerun did not audit: %s" % out)


class TestLegacyAndInterruptedRecords(_FreshnessProjectCase):
    """RED: legacy and interrupted evidence fails closed without crashing."""

    def test_conflicting_metadata_free_done_after_new_completion_fails(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        osr.Ledger().append("done", "T1", 1, fp=osr.sha_text("legacy-done-without-manifest"))
        code, out = self.audit()
        self.assertEqual(
            code, 1,
            "a second, metadata-free done record was treated as legacy instead of conflicting: %s" % out,
        )
        self.assertIn("T1", out)
        lowered = out.lower()
        self.assertTrue(
            "more than one done record" in lowered or "conflicting" in lowered,
            "conflict reason is not actionable: %s" % out,
        )

    def test_genuine_legacy_epoch_completion_is_unverified(self):
        self.build(tasks=1)
        # Rewrite the approval and the completion side into a genuine old-format
        # fixture: no state freshness block and no baseline keys on the approval.
        def strip_approval(entry):
            if entry.get("type") == "plan_approved":
                for key in ("manifest_sha", "plan_raw_sha", "ignore_sha", "approval_epoch"):
                    entry["data"].pop(key, None)

        self.rewrite_ledger(strip_approval)
        legacy_state = osr.load_state()
        legacy_state.pop("freshness", None)
        osr.save_state(legacy_state)

        code, out = self.start("T1")
        self.assertEqual(code, 0, "legacy start failed: %s" % out)
        self.assertIn("legacy", out.lower())
        self.publish("T1", 2)
        code, out = self.finish("T1")
        self.assertEqual(code, 0, "legacy completion failed: %s" % out)

        completed = osr.Ledger().latest("done", "T1", 1)
        self.assertIsNone(completed["data"]["completion"]["start_base_sha"])
        self.assertTrue(osr.Ledger().verify_chain()[0], "the legacy chain stopped verifying")
        code, out = self.audit()
        self.assertEqual(code, 2, "legacy evidence did not audit as pending review: %s" % out)
        self.assertIn("UNVERIFIED", out)
        self.assertIn("T1", out)
        self.assertIn("legacy", out.lower())

    def test_state_done_without_done_ledger_record_fails_closed(self):
        self.build(tasks=1)
        self.start("T1")
        self.publish("T1", 2)
        self.assertEqual(self.verify("T1")[0], 0)
        self.assertEqual(self.review("T1", "spec")[0], 0)
        self.assertEqual(self.review("T1", "quality")[0], 0)
        st = osr.load_state()
        st["tasks"]["T1"]["status"] = "done"
        osr.save_state(st)
        code, out = self.audit()
        self.assertEqual(
            code, 1,
            "audit trusted state.json done without a matching ledger record: %s" % out,
        )
        self.assertIn("T1", out)

    def test_ledger_done_without_state_completion_fails_closed(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        st = osr.load_state()
        st["tasks"]["T1"].pop("completion", None)
        st["tasks"]["T1"]["status"] = "in_progress"
        osr.save_state(st)
        code, out = self.audit()
        self.assertEqual(
            code, 1,
            "audit trusted a ledger done record without the matching state write: %s" % out,
        )
        self.assertIn("T1", out)
        self.assertIn("interrupted", out.lower())

    def test_corrupt_completion_record_fails_closed(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        osr.Ledger().append(
            "done", "T1", 1,
            completion={
                "schema": "osr.completion.v1",
                "approval_epoch": self.last_seq(),
                "card_sha": osr.sha_text(self.read(".ai/tasks/T1.md")),
                "config_sha": osr.sha_config(),
                "delta": {"a.py": None},
                "result_sha": "0" * 64,
                "verified_fp": "0" * 64,
            },
        )
        code, out = self.audit()
        self.assertEqual(code, 1, "a truncated completion record passed: %s" % out)
        self.assertIn("T1", out)

    def test_old_format_start_closes_as_explicit_legacy_unverified(self):
        self.build(tasks=1)
        code, out = self.start("T1")
        self.assertEqual(code, 0, "fixture start failed: %s" % out)

        def strip_to_pre_feature(entry):
            if entry.get("type") == "plan_approved":
                for key in ("manifest_sha", "plan_raw_sha", "ignore_sha", "approval_epoch"):
                    entry["data"].pop(key, None)
            if entry.get("type") == "start" and entry.get("task") == "T1":
                for key in osr.START_BINDING_KEYS:
                    entry["data"].pop(key, None)

        self.rewrite_ledger(strip_to_pre_feature)
        legacy_state = osr.load_state()
        legacy_state.pop("freshness", None)
        legacy_state["tasks"]["T1"].pop("start", None)
        osr.save_state(legacy_state)
        start_entry = osr.Ledger().latest("start", "T1", 1)
        self.assertEqual(
            set(start_entry["data"]) & set(osr.START_BINDING_KEYS), set(),
            "fixture did not remove every start binding",
        )

        self.publish("T1", 2)
        code, out = self.finish("T1")
        self.assertEqual(code, 0, "a genuine old-format start could not close: %s" % out)

        completed = osr.Ledger().latest("done", "T1", 1)
        self.assertNotIn(
            "completion", completed["data"],
            "a legacy technical closure must not invent an osr.completion.v1 certificate",
        )
        closure = completed["data"].get("legacy_closure")
        self.assertIsInstance(closure, dict)
        self.assertEqual(sorted(closure["missing_bindings"]), sorted(osr.START_BINDING_KEYS))
        self.assertIn("predates", closure["reason"])
        st_task = osr.load_state()["tasks"]["T1"]
        self.assertNotIn("completion", st_task)
        self.assertEqual(st_task["legacy_closure"], closure,
                         "state and ledger legacy closures disagree")
        self.assertEqual(st_task["status"], "done")
        ok, msg = osr.Ledger().verify_chain()
        self.assertTrue(ok, "the legacy chain stopped verifying: %s" % msg)

        code, out = self.audit()
        self.assertEqual(code, 2, "legacy closure did not audit as pending review: %s" % out)
        self.assertIn("UNVERIFIED", out)
        self.assertIn("T1", out)
        self.assertIn("legacy", out.lower())
        self.assertIn("bindings", out.lower())
        freshness = osr.evaluate_acceptance(osr.load_cfg(), osr.load_state(), osr.Ledger())
        self.assertEqual(freshness["accepted_tasks"], {},
                         "a legacy closure earned current requirement credit")

    def test_partial_new_format_start_is_rejected(self):
        self.build(tasks=1)
        code, out = self.start("T1")
        self.assertEqual(code, 0, "fixture start failed: %s" % out)

        def drop_one_binding(entry):
            if entry.get("type") == "start" and entry.get("task") == "T1":
                entry["data"].pop("card_sha", None)

        self.rewrite_ledger(drop_one_binding)
        self.publish("T1", 2)
        code, out = self.finish("T1", assert_ok=False)
        self.assertNotEqual(
            code, 0,
            "a partially bound new-format start fell back to legacy: %s" % out,
        )
        self.assertIn("partially bound", out.lower())
        self.assertIn("card_sha", out)

    def test_metadata_free_start_under_baseline_approval_is_rejected(self):
        self.build(tasks=1)
        code, out = self.start("T1")
        self.assertEqual(code, 0, "fixture start failed: %s" % out)

        def strip_all_bindings(entry):
            if entry.get("type") == "start" and entry.get("task") == "T1":
                for key in osr.START_BINDING_KEYS:
                    entry["data"].pop(key, None)

        self.rewrite_ledger(strip_all_bindings)
        self.publish("T1", 2)
        code, out = self.finish("T1", assert_ok=False)
        self.assertNotEqual(
            code, 0,
            "a metadata-free start was closed as legacy under a baseline-backed approval: %s" % out,
        )
        self.assertIn("baseline", out.lower())
        self.assertIn("bindings", out.lower())

    def test_legacy_ledger_chain_remains_readable(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        osr.Ledger().append("done", "T1", 1, fp=osr.sha_text("legacy-done-without-manifest"))
        ok, msg = osr.Ledger().verify_chain()
        self.assertTrue(ok, "a legacy chain entry broke ledger verification: %s" % msg)


class TestApprovalBinding(_FreshnessProjectCase):
    """The approval baseline is anchored in the ledger, not self-certified by state."""

    def test_state_baseline_self_digest_tamper_is_rejected(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        st = osr.load_state()
        fresh = st["freshness"]
        tampered = dict(fresh["manifest"])
        tampered[sorted(tampered)[0]] = "0" * 64
        fresh["manifest"] = tampered
        # Re-sign the state with its own new digest; only the ledger is untouched.
        fresh["manifest_sha"] = canon_digest(tampered)
        osr.save_state(st)
        ledger_sha = osr.Ledger().latest("plan_approved")["data"]["manifest_sha"]
        self.assertNotEqual(ledger_sha, fresh["manifest_sha"],
                            "fixture did not actually diverge from the ledger commitment")
        code, out = self.audit()
        self.assertEqual(code, 1, "a self-re-signed baseline passed audit: %s" % out)
        self.assertIn("baseline", out.lower())

    def test_crlf_plan_approval_binding_is_consistent(self):
        self.build(tasks=1)
        crlf = PLAN_ONE.replace("\n", "\r\n").encode("utf-8")
        self.write_bytes(".ai/PLAN.md", crlf)
        code, out = self.call(osr.cmd_approve, argparse.Namespace(by=["human"], secret=None))
        self.assertEqual(code, 0, "re-approval of a CRLF plan failed: %s" % out)
        st = osr.load_state()
        fresh = st["freshness"]
        normalized = osr.sha_text(osr.ai("PLAN.md").read_text(encoding="utf-8"))
        self.assertNotEqual(
            fresh["plan_raw_sha"], normalized,
            "fixture did not exercise raw CRLF bytes versus the normalised plan text",
        )
        self.assertEqual(fresh["plan_hash"], normalized)
        self.assertEqual(fresh["plan_raw_sha"], raw_sha(osr.ai("PLAN.md")))
        self.assertEqual(
            osr.Ledger().latest("plan_approved")["data"]["plan_raw_sha"],
            fresh["plan_raw_sha"],
        )
        self.complete_ok("T1", 2)
        code, out = self.audit()
        self.assertEqual(code, 0, "a CRLF-approved plan did not audit: %s" % out)

    def test_approval_is_rejected_while_a_task_is_in_progress(self):
        self.build(tasks=1)
        before = osr.load_state()["freshness"]["epoch"]
        code, out = self.start("T1")
        self.assertEqual(code, 0, "start failed: %s" % out)
        code, out = self.call(osr.cmd_approve, argparse.Namespace(by=["human"], secret=None))
        self.assertNotEqual(code, 0, "approval silently rebased an active task: %s" % out)
        self.assertIn("T1", out)
        self.assertIn("in_progress", out.lower())
        self.assertEqual(osr.load_state()["freshness"]["epoch"], before,
                         "a rejected approval still rewrote the approval epoch")


class TestStartLineage(_FreshnessProjectCase):
    """Start bindings make a completion describe exactly the bytes it verified."""

    def test_second_active_start_is_rejected(self):
        self.build(tasks=2)
        code, out = self.start("T1")
        self.assertEqual(code, 0, "start failed: %s" % out)
        code, out = self.start("T2")
        self.assertNotEqual(code, 0, "a second task started concurrently: %s" % out)
        self.assertIn("T1", out)
        self.assertIn("in_progress", out.lower())

    def test_card_change_mid_attempt_is_rejected(self):
        self.build(tasks=1)
        code, out = self.start("T1")
        self.assertEqual(code, 0, "start failed: %s" % out)
        card = self.read(".ai/tasks/T1.md")
        self.write(
            ".ai/tasks/T1.md",
            card.replace("allowed_files: a.py", "allowed_files: a.py, b.py"),
        )
        self.publish("T1", 2)
        self.write("b.py", "OTHER = 99\n")
        code, out = self.finish("T1", assert_ok=False)
        self.assertNotEqual(code, 0, "a card changed mid-attempt expanded its scope: %s" % out)
        self.assertIn("card", out.lower())

    def test_mismatched_verified_fingerprint_is_rejected(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        forged = "1" * 64

        def mutate(entry):
            if entry.get("type") == "done" and entry.get("task") == "T1":
                entry["data"]["completion"]["verified_fp"] = forged

        self.rewrite_ledger(mutate)
        st = osr.load_state()
        st["tasks"]["T1"]["completion"]["verified_fp"] = forged
        osr.save_state(st)
        code, out = self.audit()
        self.assertEqual(code, 1, "a forged verify binding passed audit: %s" % out)
        self.assertIn("fingerprint", out.lower())


class TestLegitimateEvolution(_FreshnessProjectCase):
    """Accepted later tasks may add, delete and recreate governed files."""

    def test_legitimate_addition_deletion_and_recreation_audit(self):
        self.build(tasks=3)
        self.complete_ok("T1", 2)

        code, out = self.waive(
            "T2", "deleted:b.py",
            "b.py is intentionally replaced by c.py for this task",
        )
        self.assertEqual(code, 0, "deletion waiver failed: %s" % out)
        code, out = self.start("T2")
        self.assertEqual(code, 0, "start failed: %s" % out)
        self.write("a.py", "VALUE = 3\n")
        self.write("c.py", "C = 1\n")
        self.remove("b.py")
        self.write(".ai/reviews/T2.spec.md", 'R2: PASS @ c.py:1 "C = 1"\n\nVERDICT: PASS\n')
        self.write(".ai/reviews/T2.quality.md", QUALITY_BODY)
        code, out = self.finish("T2")
        self.assertEqual(code, 0, "a legitimate addition/deletion was rejected: %s" % out)

        code, out = self.start("T3")
        self.assertEqual(code, 0, "start after a legitimate deletion failed: %s" % out)
        self.write("b.py", "OTHER = 7\n")
        self.write(".ai/reviews/T3.spec.md", 'R3: PASS @ b.py:1 "OTHER = 7"\n\nVERDICT: PASS\n')
        self.write(".ai/reviews/T3.quality.md", QUALITY_BODY)
        code, out = self.finish("T3")
        self.assertEqual(code, 0, "a legitimate recreation was rejected: %s" % out)

        code, out = self.audit()
        self.assertEqual(code, 0, "legitimate add/delete/recreate did not audit: %s" % out)


class TestReadOnlyAudit(_FreshnessProjectCase):
    """RED: audit --check must validate without writing project files."""

    def test_audit_check_preserves_all_bytes_on_clean_outcome(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        before = self.snapshot_all()
        entries_before = len(self.ledger_entries())
        code, out = self.cli("audit", "--check")
        self.assertEqual(code, 0, "audit --check is not a supported read-only path: %s" % out)
        self.assertIn("AUDIT", out)
        self.assertEqual(before, self.snapshot_all(), "audit --check modified project files")
        self.assertEqual(len(self.ledger_entries()), entries_before,
                         "audit --check appended to the ledger")

    def test_audit_check_preserves_all_bytes_on_stale_outcome(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        self.write("a.py", "VALUE = 666\n")
        before = self.snapshot_all()
        code, out = self.cli("audit", "--check")
        self.assertEqual(code, 1, "audit --check missed the stale bytes: %s" % out)
        self.assertIn("a.py", out)
        self.assertEqual(before, self.snapshot_all(),
                         "a failing audit --check modified project files")

    def test_audit_check_reports_the_same_verdict_as_reporting_audit(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        write_code, write_out = self.audit()
        self.assertEqual(write_code, 0, write_out)
        check_code, check_out = self.cli("audit", "--check")
        self.assertEqual(check_code, write_code, "audit --check disagrees with audit")
        for marker in ("VERIFIED", "PASS"):
            self.assertIn(marker, check_out)

    def test_repeated_reporting_audit_runs_no_commands(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        entries_before = len(self.ledger_entries())
        with mock.patch.object(
            osr, "run_recorded",
            side_effect=AssertionError("audit must not execute verification commands"),
        ):
            first_code, first_out = self.audit()
            second_code, second_out = self.audit()
        self.assertEqual(first_code, 0, first_out)
        self.assertEqual(second_code, 0, second_out)
        self.assertEqual(len(self.ledger_entries()), entries_before,
                         "audit appended to the ledger")


class TestMutationLockBoundaries(_FreshnessProjectCase):
    """RED: preconditions must be rechecked from current state under the lock."""

    def test_approval_rechecks_active_task_after_lock_acquisition(self):
        self.build(tasks=1)
        approved_before = [
            e for e in self.ledger_entries() if e.get("type") == "plan_approved"
        ]
        real_enter = osr.LedgerLock.__enter__
        fired = {"done": False}

        def activate_then_enter(lock_self):
            if not fired["done"]:
                fired["done"] = True
                # A real task becomes active just as the approval lock is taken.
                st = osr.load_state()
                ts = osr.task_state(st, "T1")
                ts["status"] = "in_progress"
                ts["attempts"] = 1
                osr.save_state(st)
            return real_enter(lock_self)

        with mock.patch.object(osr.LedgerLock, "__enter__", activate_then_enter):
            code, out = self.call(
                osr.cmd_approve, argparse.Namespace(by=["human"], secret=None)
            )
        self.assertNotEqual(
            code, 0,
            "approval overwrote a task that became active while it waited: %s" % out,
        )
        self.assertIn("T1", out)
        self.assertIn("in_progress", out.lower())
        saved = osr.load_state()["tasks"]
        self.assertIn("T1", saved, "approval erased the newly active task entry")
        self.assertEqual(saved["T1"]["status"], "in_progress")
        approved_after = [
            e for e in self.ledger_entries() if e.get("type") == "plan_approved"
        ]
        self.assertEqual(len(approved_after), len(approved_before),
                         "a rejected approval still appended a new epoch")

    def test_duplicate_start_rechecks_task_lineage_under_lock(self):
        self.build(tasks=1)
        real_enter = osr.LedgerLock.__enter__
        fired = {"done": False}

        def inner_start_then_enter(lock_self):
            if not fired["done"]:
                fired["done"] = True
                inner_code, inner_out = self.start("T1")
                self.assertEqual(inner_code, 0, "inner start failed: %s" % inner_out)
            return real_enter(lock_self)

        with mock.patch.object(osr.LedgerLock, "__enter__", inner_start_then_enter):
            code, out = self.start("T1")
        self.assertNotEqual(
            code, 0,
            "a queued start advanced the same task from attempt 1 to 2 without triage: %s" % out,
        )
        starts = [
            e for e in self.ledger_entries()
            if e.get("type") == "start" and e.get("task") == "T1"
        ]
        self.assertEqual(len(starts), 1, "the duplicate start appended a second attempt")
        self.assertEqual(starts[0]["attempt"], 1)
        self.assertEqual(osr.load_state()["tasks"]["T1"]["attempts"], 1)


class TestBaselineColdReplay(_FreshnessProjectCase):
    """RED: durable baseline evidence must not require the ignored snapshot cache."""

    def test_baseline_replay_without_local_snapshot_cache_succeeds(self):
        self.build(tasks=2)
        self.complete_ok("T1", 2)
        self.complete_ok("T2", 3)
        for tid in ("T1", "T2"):
            self.remove(".ai/snapshots/%s.json" % tid)
        self.assertFalse(osr.snap_path("T1").exists())
        self.assertFalse(osr.snap_path("T2").exists())

        before = self.snapshot_all()
        entries_before = len(self.ledger_entries())
        code, out = self.cli("audit", "--check")
        self.assertEqual(
            code, 0,
            "baseline-backed evidence still required an ignored local snapshot: %s" % out,
        )
        self.assertEqual(before, self.snapshot_all(),
                         "cold-replay audit --check modified project files")
        self.assertEqual(len(self.ledger_entries()), entries_before,
                         "cold-replay audit --check appended to the ledger")

        code, out = self.audit()
        self.assertEqual(
            code, 0,
            "reporting audit rejected a baseline replay that had no snapshot cache: %s" % out,
        )

    def test_conflicting_cached_snapshot_is_rejected(self):
        self.build(tasks=1)
        self.complete_ok("T1", 2)
        snap_file = osr.snap_path("T1")
        data = json.loads(snap_file.read_text(encoding="utf-8"))
        first = sorted(data)[0]
        data[first]["sha"] = "0" * 64
        snap_file.write_text(json.dumps(data), encoding="utf-8")

        before = self.snapshot_all()
        code, out = self.cli("audit", "--check")
        self.assertEqual(
            code, 1,
            "a conflicting cached snapshot silently overrode the bound start map: %s" % out,
        )
        self.assertIn("snapshot", out.lower())
        self.assertEqual(before, self.snapshot_all(),
                         "a failing cold-replay audit --check modified project files")


if __name__ == "__main__":
    unittest.main()
