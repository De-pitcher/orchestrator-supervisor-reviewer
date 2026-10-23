"""Regression tests for R24 (T26): commit the audited artifact.

The goal of the commit gate is that the bytes Git is about to record are the
bytes the workflow audited, and that the workflow evidence is current. These
tests drive a real Git repository with a real temporary index and invoke the
actual hook process; they never simulate an index in memory.

The suite covers three groups:

* evidence attacks: an incomplete task, stale completion evidence, a changed
  card or a broken ledger are rejected by the read-only ``audit --check``;
* staged-byte parity: the hook reads the complete proposed index with NUL-safe
  Git plumbing, so partial staging, staged additions/deletions, index-only
  blobs, stale governance bytes and essential governance restored to HEAD are
  all rejected even when ``git diff --cached`` does not name the path;
* normalization and layout controls: pure CRLF/LF differences are accepted for
  Git's real text treatment (``text``, ``text=auto``, ``core.autocrlf``), while
  ``-text``/``binary``, NUL data, bare carriage returns and non-newline byte
  changes are rejected; unsupported filters/encodings fail with a diagnostic.
  The wrapper is exercised through real Git for both documented layouts.

A repository without an OSR workflow is permitted. Hook execution is asserted
to leave the raw ``.git/index`` bytes, every project file and the configured
runner counter unchanged.

Run: python -m unittest discover -s tests -p test_commit_gate.py -v
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import scripts.osr as osr

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_SRC = REPO_ROOT / "integrations" / "git" / "pre_commit.py"
WRAPPER_SRC = REPO_ROOT / "integrations" / "git" / "pre-commit"
OSR_SRC = REPO_ROOT / "scripts" / "osr.py"


def quoted_python():
    return '"%s"' % sys.executable


# The declared runner both emits real unittest-shaped output and records that a
# configured command really executed, so a hook cannot run it unnoticed.
RUNNER = (
    "import pathlib\n"
    "import sys\n"
    "p = pathlib.Path('.ai/runner-runs.txt')\n"
    "p.parent.mkdir(parents=True, exist_ok=True)\n"
    "with p.open('a', encoding='utf-8') as fh:\n"
    "    fh.write('ran %s\\n' % (sys.argv[1] if len(sys.argv) > 1 else 'test_unknown'))\n"
    "name = sys.argv[1] if len(sys.argv) > 1 else 'test_unknown'\n"
    "sys.stdout.write('%s (proj.Suite.%s) ... ok\\n' % (name, name))\n"
    "sys.stdout.write('\\n----------------------------------------------------------------------\\n')\n"
    "sys.stdout.write('Ran 1 test in 0.001s\\n\\nOK\\n')\n"
)

PLAN_ONE = """# Plan
## Goal
Prove the commit gate checks the audited artifact.
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
Prove the commit gate checks the audited artifact.
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

SPACE_PATH = "space dir/notes file.py"
CRLF_PATH = "ntext.txt"
U16_PATH = "u16.txt"
U16_BYTES = "LINE = 1\n".encode("utf-16-le")
AUTOCRLF_PATH = "autocrlf.txt"
TEXTAUTO_PATH = "textauto.txt"
BINTEXT_PATH = "bintext.txt"
BYTEDIFF_PATH = "bytediff.txt"
TEXTAUTO_BIN_PATH = "textauto-bin.txt"


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def snapshot_tree(root):
    """Every project file except Git internals: relative path -> sha256."""
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        out[rel] = sha_bytes(p.read_bytes())
    return out


class TestCommitGateCleanControl(unittest.TestCase):
    """Activation controls that already hold before the T26 change."""

    def test_clean_control_no_workflow_hook(self):
        """A directory with no OSR workflow and no tooling is permitted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            hook_dest = Path(tmpdir) / "pre_commit.py"
            shutil.copy(HOOK_SRC, hook_dest)

            res = subprocess.run(
                [sys.executable, str(hook_dest)],
                cwd=tmpdir, capture_output=True, text=True,
            )
            self.assertEqual(
                res.returncode, 0,
                "Expected 0 exit, got %d:\n%s\n%s" % (res.returncode, res.stdout, res.stderr),
            )

    def test_clean_control_no_workflow_with_tooling_present(self):
        """A repository without .ai/ is permitted even when osr.py is installed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "scripts").mkdir()
            shutil.copy(OSR_SRC, root / "scripts" / "osr.py")
            (root / "integrations" / "git").mkdir(parents=True)
            helper = root / "integrations" / "git" / "pre_commit.py"
            shutil.copy(HOOK_SRC, helper)
            (root / "app.py").write_text("VALUE = 1\n", encoding="utf-8")

            res = subprocess.run(
                [sys.executable, str(helper)],
                cwd=tmpdir, capture_output=True, text=True,
            )
            self.assertEqual(
                res.returncode, 0,
                "A repository with no OSR workflow must not be blocked, got %d:\n%s\n%s"
                % (res.returncode, res.stdout, res.stderr),
            )


class _CommitGateCase(unittest.TestCase):
    """Build a real repository, a real completed workflow and a real index."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self._old_root = osr.ROOT
        self._old_json = osr.JSON_MODE
        osr.ROOT = self.repo
        osr.JSON_MODE = False
        for name in ("tasks", "logs", "snapshots", "reviews"):
            osr.ai(name).mkdir(parents=True, exist_ok=True)
        self.git("init", "-b", "main")
        self.git("config", "user.email", "builder@example.test")
        self.git("config", "user.name", "Builder")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.autocrlf", "false")

    def tearDown(self):
        osr.JSON_MODE = self._old_json
        osr.ROOT = self._old_root
        self._tmp.cleanup()

    # -- process helpers ------------------------------------------------------
    def git_env(self):
        env = os.environ.copy()
        env["GIT_OPTIONAL_LOCKS"] = "0"
        return env

    def git(self, *args, check=True, input=None):
        kwargs = {
            "cwd": str(self.repo),
            "capture_output": True,
            "timeout": 180,
            "env": self.git_env(),
        }
        if input is None:
            kwargs["text"] = True
        proc = subprocess.run(["git"] + list(args), input=input, **kwargs)
        if check and proc.returncode != 0:
            stdout = proc.stdout.decode("utf-8", "replace") if isinstance(proc.stdout, bytes) else proc.stdout
            stderr = proc.stderr.decode("utf-8", "replace") if isinstance(proc.stderr, bytes) else proc.stderr
            raise AssertionError(
                "git %s failed (%d):\n%s\n%s"
                % (" ".join(args), proc.returncode, stdout, stderr)
            )
        return proc

    def run_helper(self, helper=None, timeout=240, env=None):
        helper = helper or (self.repo / "integrations" / "git" / "pre_commit.py")
        self.assertTrue(Path(helper).is_file(), "hook helper missing: %s" % helper)
        return subprocess.run(
            [sys.executable, str(helper)], cwd=str(self.repo),
            capture_output=True, text=True, timeout=timeout, env=env,
        )

    def hook_output(self, proc):
        return (proc.stdout or "") + (proc.stderr or "")

    def assert_rejected(self, proc, *needles):
        out = self.hook_output(proc)
        self.assertNotEqual(
            proc.returncode, 0,
            "hook accepted a commit it must reject:\n%s" % out,
        )
        self.assertTrue(out.strip(), "hook rejected without any diagnostic output")
        for needle in needles:
            self.assertIn(
                needle, out,
                "diagnostic does not mention %r:\n%s" % (needle, out),
            )

    def assert_accepted(self, proc):
        self.assertEqual(
            proc.returncode, 0,
            "hook rejected a commit it must accept (%d):\n%s"
            % (proc.returncode, self.hook_output(proc)),
        )

    def index_entries(self):
        return self.git("ls-files", "-s").stdout

    def index_file_bytes(self):
        """Raw bytes of the real index file; any refresh is still a write."""
        return (self.repo / ".git" / "index").read_bytes()

    def cached_changed_names(self):
        raw = self.git("diff", "--cached", "--name-only", "-z").stdout
        return [name for name in raw.split("\0") if name]

    def restore_index_from_head(self, rel):
        """Put HEAD's blob back in the index but leave the working file alone."""
        self.git("reset", "-q", "HEAD", "--", rel)

    def staged_bytes(self, rel):
        return subprocess.run(
            ["git", "show", ":" + rel], cwd=str(self.repo),
            capture_output=True, timeout=60,
        ).stdout

    def write_index_blob(self, rel, data):
        """Write a real blob object and place it in the real index."""
        oid = self.git("hash-object", "-w", "--stdin", input=data).stdout.decode("ascii").strip()
        self.git("update-index", "--cacheinfo", "100644,%s,%s" % (oid, rel))
        return oid

    def path_entry_has_osr(self, entry):
        extensions = [""] + [e for e in os.environ.get("PATHEXT", "").split(os.pathsep) if e]
        for ext in extensions:
            if (Path(entry) / ("osr" + ext)).exists():
                return True
        return False

    def path_without_osr(self):
        """Keep the real PATH but remove any directory that could supply ``osr``."""
        entries = [e for e in os.environ.get("PATH", "").split(os.pathsep) if e]
        return os.pathsep.join(e for e in entries if not self.path_entry_has_osr(e))

    def env_with_path(self, entries):
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join(str(e) for e in entries)
        env["GIT_OPTIONAL_LOCKS"] = "0"
        return env

    def make_external_osr(self):
        """Install a throwaway external ``osr`` CLI outside the fixture repo."""
        external = self.base / "external"
        external.mkdir(exist_ok=True)
        osr_copy = external / "osr.py"
        shutil.copy(OSR_SRC, osr_copy)
        fakebin = self.base / "fakebin"
        fakebin.mkdir(exist_ok=True)
        shell = fakebin / "osr"
        shell.write_text(
            '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, osr_copy),
            encoding="utf-8",
        )
        os.chmod(shell, 0o755)
        (fakebin / "osr.cmd").write_text(
            '@"%s" "%s" %%*\n' % (sys.executable, osr_copy),
            encoding="utf-8",
        )
        return fakebin

    # -- in-process handler drivers ------------------------------------------
    def call(self, fn, ns):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                fn(ns)
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
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

    # -- file helpers ---------------------------------------------------------
    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def write_bytes(self, rel, data):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    # -- project construction -------------------------------------------------
    def build(self, tasks=1, complete=("T1",), install_helper=True):
        """Create, approve, commit and (optionally) fully verify a workflow."""
        self.write("run_checks.py", RUNNER)
        self.write("a.py", "VALUE = 1\n")
        self.write("b.py", "OTHER = 0\n")
        self.write(SPACE_PATH, "SPACED = 1\n")
        self.write_bytes(CRLF_PATH, b"alpha\r\nbeta\r\n")
        self.write_bytes(U16_PATH, U16_BYTES)
        # Real normalization fixtures. ``autocrlf.txt`` has no attribute,
        # ``textauto.txt`` uses Git's content-based text detection,
        # ``bintext.txt`` opts out with ``-text`` and ``bytediff.txt`` is text
        # but only differs from its staged blob by a non-newline byte in one
        # attack. ``textauto-bin.txt`` carries NUL bytes under ``text=auto``.
        self.write_bytes(AUTOCRLF_PATH, b"auto\r\nline\r\n")
        self.write_bytes(TEXTAUTO_PATH, b"autoattr\r\nline\r\n")
        self.write_bytes(BINTEXT_PATH, b"bintext\r\nline\r\n")
        self.write_bytes(BYTEDIFF_PATH, b"bytediff\r\nline\r\n")
        self.write_bytes(TEXTAUTO_BIN_PATH, b"auto\x00bin\r\nline\x00\r\n")
        self.write(
            ".gitattributes",
            "\n".join([
                "ntext.txt text",
                "%s text=auto" % TEXTAUTO_PATH,
                "%s -text" % BINTEXT_PATH,
                "%s text" % BYTEDIFF_PATH,
                "%s text=auto" % TEXTAUTO_BIN_PATH,
                "",
            ]),
        )
        self.write(".ai/PLAN.md", PLAN_TWO if tasks == 2 else PLAN_ONE)

        commands = {}
        for i in range(1, tasks + 1):
            tid = "T%d" % i
            req = "R%d" % i
            cmd = "%s run_checks.py %s" % (
                quoted_python(), "test_alpha" if i == 1 else "test_beta",
            )
            commands["check_" + tid.lower()] = {"cmd": cmd, "verified": True}
            self.write(
                ".ai/tasks/%s.md" % tid,
                CARD.format(
                    tid=tid,
                    req=req,
                    depends="depends_on: T1\n" if i > 1 else "",
                    allowed="a.py" if i == 1 else "a.py, b.py",
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

        # Enforcement tooling is part of the governed tree, so it is written
        # before approval and before the baseline commit. Layout-specific
        # wrapper tests can opt out so the integrations fallback cannot mask
        # the helper they are actually exercising.
        (self.repo / "scripts").mkdir(exist_ok=True)
        shutil.copy(OSR_SRC, self.repo / "scripts" / "osr.py")
        if install_helper:
            (self.repo / "integrations" / "git").mkdir(parents=True, exist_ok=True)
            shutil.copy(HOOK_SRC, self.repo / "integrations" / "git" / "pre_commit.py")

        code, out = self.call(osr.cmd_approve, argparse.Namespace(by=["human"], secret=None))
        self.assertEqual(code, 0, "fixture approval failed: %s" % out)
        self.git("add", "-A")
        self.git("commit", "-m", "baseline")

        for tid in complete:
            self.complete(tid)
        self.git("add", "-A")

    def publish(self, tid, value):
        num = tid[1:]
        self.write("a.py", "VALUE = %s\n" % value)
        self.write(".ai/reviews/%s.spec.md" % tid, SPEC_TEMPLATE.format(num=num, value=value))
        self.write(".ai/reviews/%s.quality.md" % tid, QUALITY_BODY)

    def complete(self, tid, value=1):
        code, out = self.start(tid)
        self.assertEqual(code, 0, "start %s failed: %s" % (tid, out))
        self.publish(tid, value)
        for label, step in (
            ("verify", lambda: self.verify(tid)),
            ("spec review", lambda: self.review(tid, "spec")),
            ("quality review", lambda: self.review(tid, "quality")),
        ):
            code, out = step()
            self.assertEqual(code, 0, "%s %s failed: %s" % (label, tid, out))
        code, out = self.done(tid)
        self.assertEqual(code, 0, "done %s failed: %s" % (tid, out))

    # -- audit control --------------------------------------------------------
    def audit_check(self):
        return subprocess.run(
            [sys.executable, str(self.repo / "scripts" / "osr.py"),
             "--root", str(self.repo), "audit", "--check"],
            cwd=str(self.repo), capture_output=True, text=True, timeout=240,
        )


class TestVerifiedWorkflowControls(_CommitGateCase):
    """A clean, fully verified workflow must keep committing."""

    def test_clean_control_audit_check_passes(self):
        """Fixture guard: T25's read-only audit accepts this project."""
        self.build()
        res = self.audit_check()
        self.assertEqual(
            res.returncode, 0,
            "fixture must audit clean before the hook is judged:\n%s\n%s"
            % (res.stdout, res.stderr),
        )

    def test_verified_staged_workflow_passes(self):
        self.build()
        proc = self.run_helper()
        self.assert_accepted(proc)

    def test_path_with_spaces_clean_control_passes(self):
        self.build()
        self.assertIn(SPACE_PATH, self.git("ls-files").stdout)
        self.assert_accepted(self.run_helper())

    def test_line_ending_normalization_control_passes(self):
        """Staged LF bytes for a CRLF working file are Git normalization."""
        self.build()
        staged = self.staged_bytes(CRLF_PATH)
        disk = (self.repo / CRLF_PATH).read_bytes()
        self.assertNotIn(b"\r", staged, "fixture did not normalize the staged blob")
        self.assertIn(b"\r", disk, "fixture did not keep CRLF on disk")
        self.assert_accepted(self.run_helper())

    def test_core_autocrlf_normalization_control_passes(self):
        """core.autocrlf normalization is allowed for real Git text treatment."""
        self.build()
        self.git("config", "core.autocrlf", "true")
        self.git("add", "--renormalize", AUTOCRLF_PATH)
        staged = self.staged_bytes(AUTOCRLF_PATH)
        disk = (self.repo / AUTOCRLF_PATH).read_bytes()
        self.assertNotEqual(staged, disk, "core.autocrlf did not change the staged blob")
        self.assertNotIn(b"\r", staged, "core.autocrlf did not normalize the staged blob")
        self.assertIn(b"\r", disk, "fixture lost the CRLF working bytes")
        self.assert_accepted(self.run_helper())

    def test_text_auto_normalization_control_passes(self):
        """text=auto with ordinary text may normalize CRLF to LF."""
        self.build()
        self.git("add", "--renormalize", TEXTAUTO_PATH)
        staged = self.staged_bytes(TEXTAUTO_PATH)
        disk = (self.repo / TEXTAUTO_PATH).read_bytes()
        self.assertNotEqual(staged, disk, "text=auto did not change the staged blob")
        self.assertNotIn(b"\r", staged, "text=auto did not normalize the staged blob")
        self.assertIn(b"\r", disk, "fixture lost the CRLF working bytes")
        self.assert_accepted(self.run_helper())

    def test_negative_text_override_exact_bytes_control_passes(self):
        """-text keeps raw bytes even when core.autocrlf would normalize."""
        self.build()
        self.git("config", "core.autocrlf", "true")
        self.git("add", "--renormalize", BINTEXT_PATH)
        staged = self.staged_bytes(BINTEXT_PATH)
        disk = (self.repo / BINTEXT_PATH).read_bytes()
        self.assertEqual(staged, disk, "-text must not be overridden by core.autocrlf")
        self.assertIn(b"\r", staged, "fixture did not keep the -text raw bytes")
        self.assert_accepted(self.run_helper())

    def test_hook_writes_no_evidence_and_runs_no_commands_on_pass(self):
        self.build()
        before_files = snapshot_tree(self.repo)
        before_index = self.index_entries()
        before_index_bytes = self.index_file_bytes()
        before_runs = (self.repo / ".ai" / "runner-runs.txt").read_bytes()

        self.assert_accepted(self.run_helper())

        self.assertEqual(self.index_entries(), before_index, "index entries changed during a passing hook")
        self.assertEqual(
            self.index_file_bytes(), before_index_bytes,
            "the raw index file changed during a passing hook (a stat refresh is still a write)",
        )
        self.assertEqual(snapshot_tree(self.repo), before_files, "hook modified project files")
        self.assertEqual(
            (self.repo / ".ai" / "runner-runs.txt").read_bytes(), before_runs,
            "hook executed the configured test command",
        )


class TestEvidenceAttacks(_CommitGateCase):
    """The hook must reject commits without current evidence."""

    def test_incomplete_task_is_rejected(self):
        self.build(tasks=2, complete=("T1",))
        self.assert_rejected(self.run_helper(), "T2")

    def test_stale_working_file_after_completion_is_rejected(self):
        self.build()
        self.write("a.py", "VALUE = 99\n")
        self.git("add", "a.py")
        self.assert_rejected(self.run_helper(), "a.py")

    def test_widened_card_after_completion_is_rejected(self):
        self.build()
        card = self.repo / ".ai" / "tasks" / "T1.md"
        card.write_text(
            card.read_text(encoding="utf-8").replace(
                "allowed_files: a.py", "allowed_files: a.py, b.py"
            ),
            encoding="utf-8",
        )
        self.assert_rejected(self.run_helper(), "T1")

    def test_broken_ledger_is_rejected(self):
        self.build()
        ledger = self.repo / ".ai" / "ledger.jsonl"
        with ledger.open("a", encoding="utf-8") as fh:
            fh.write('{"seq": 999, "type": "done", "task": "T1"}\n')
        self.assert_rejected(self.run_helper(), "ledger")

    def test_initialized_workflow_missing_tooling_is_rejected(self):
        self.build()
        (self.repo / "scripts" / "osr.py").unlink()
        self.git("add", "-A")
        # Remove any accidental global ``osr`` from PATH so this exercises the
        # missing-tooling rule itself, not the host's installations.
        env = self.env_with_path([self.path_without_osr()])
        self.assert_rejected(self.run_helper(env=env), "osr")

    def test_removed_local_tooling_with_external_cli_is_rejected_as_drift(self):
        """External tooling must not hide a deleted governed local script."""
        self.build()
        (self.repo / "scripts" / "osr.py").unlink()
        self.git("add", "-A")
        fakebin = self.make_external_osr()
        env = self.env_with_path([fakebin, self.path_without_osr()])
        self.assert_rejected(self.run_helper(env=env), "scripts/osr.py")


class TestStagedByteParity(_CommitGateCase):
    """The index must carry the audited working bytes."""

    def stage_older_version(self, rel, older, current):
        """Stage ``older`` then leave ``current`` on disk (partial staging)."""
        p = self.repo / rel
        p.write_bytes(older)
        self.git("add", rel)
        p.write_bytes(current)

    def test_partial_staging_is_rejected(self):
        """Card example: stage a-b while only a+b on disk is verified."""
        self.build()
        rel = "a.py"
        current = (self.repo / rel).read_bytes()
        self.stage_older_version(rel, b"VALUE = 0\n", current)
        self.assert_rejected(self.run_helper(), rel)
        self.assertEqual((self.repo / rel).read_bytes(), current, "fixture lost the verified bytes")

    def test_partial_staging_after_restaging_passes(self):
        self.build()
        rel = "a.py"
        current = (self.repo / rel).read_bytes()
        self.stage_older_version(rel, b"VALUE = 0\n", current)
        self.assert_rejected(self.run_helper(), rel)

        self.git("add", rel)
        self.assert_accepted(self.run_helper())

    def test_staged_addition_is_rejected(self):
        self.build()
        self.write("added.py", "EXTRA = 1\n")
        self.git("add", "added.py")
        self.assert_rejected(self.run_helper(), "added.py")

    def test_index_only_addition_is_rejected(self):
        """The extra blob is only in the index, so audit's tree is clean."""
        self.build()
        self.write("added.py", "EXTRA = 1\n")
        self.git("add", "added.py")
        (self.repo / "added.py").unlink()
        self.assertFalse((self.repo / "added.py").exists(), "fixture left the working copy")
        res = self.audit_check()
        self.assertEqual(
            res.returncode, 0,
            "fixture must leave the audited working tree clean:\n%s\n%s"
            % (res.stdout, res.stderr),
        )
        self.assert_rejected(self.run_helper(), "added.py")

    def test_verified_working_file_with_head_index_is_rejected(self):
        """A verified file absent from cached-change names still needs staging."""
        self.build(tasks=2, complete=("T1",))
        self.complete("T2", value=2)
        self.git("add", "-A")
        self.assertIn("a.py", self.cached_changed_names(), "fixture did not stage the new a.py")
        self.restore_index_from_head("a.py")
        self.assertNotIn(
            "a.py", self.cached_changed_names(),
            "HEAD's a.py must be absent from the cached-change names",
        )
        self.assertNotEqual(
            self.staged_bytes("a.py"), (self.repo / "a.py").read_bytes(),
            "fixture did not restore HEAD's older blob",
        )
        self.assert_rejected(self.run_helper(), "a.py")
        self.git("add", "a.py")
        self.assert_accepted(self.run_helper())

    def test_essential_state_with_head_index_is_rejected(self):
        """Essential governance is checked even when it is not a cached change."""
        self.build()
        self.git("add", "-A")
        self.assertIn(
            ".ai/state.json", self.cached_changed_names(),
            "fixture did not stage the current state.json",
        )
        self.restore_index_from_head(".ai/state.json")
        self.assertNotIn(
            ".ai/state.json", self.cached_changed_names(),
            "HEAD's state.json must be absent from the cached-change names",
        )
        self.assert_rejected(self.run_helper(), "state.json")
        self.git("add", ".ai/state.json")
        self.assert_accepted(self.run_helper())

    def test_staged_deletion_of_governed_file_is_rejected(self):
        self.build()
        self.git("rm", "--cached", "b.py")
        self.assertTrue((self.repo / "b.py").is_file(), "fixture removed the working file")
        self.assert_rejected(self.run_helper(), "b.py")

    def test_staged_governance_removal_is_rejected(self):
        """An initialized workflow must keep its governance files staged."""
        self.build()
        self.git("rm", "--cached", ".ai/ledger.jsonl")
        self.assert_rejected(self.run_helper(), "ledger.jsonl")

    def test_stale_staged_governance_bytes_are_rejected(self):
        """Disk evidence is current but the index carries an older copy."""
        self.build()
        rel = ".ai/ledger.jsonl"
        current = (self.repo / rel).read_bytes()
        self.git("rm", "--cached", rel)
        self.stage_older_version(rel, b"", current)
        self.assert_rejected(self.run_helper(), rel)

    def test_staged_governance_file_with_modified_worktree_is_rejected(self):
        """.ai/ is not in the audited manifest, so it needs its own byte check."""
        self.build()
        rel = ".ai/config.json"
        current = (self.repo / rel).read_bytes()
        self.stage_older_version(rel, current.replace(b'"max_attempts": 3', b'"max_attempts": 9'), current)
        self.assert_rejected(self.run_helper(), rel)

    def test_unsupported_staged_transformation_is_rejected(self):
        """A per-repo attribute that rewrites bytes cannot be verified."""
        self.build()
        rel = U16_PATH
        disk = (self.repo / rel).read_bytes()
        self.assertEqual(disk, U16_BYTES, "fixture lost the working-tree bytes")

        # .git/info/attributes is repository metadata, not governed content, so
        # the audited working tree stays clean while the staged blob is rewritten
        # from UTF-16LE to UTF-8 on checkin.
        info = self.repo / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "attributes").write_text(
            "%s working-tree-encoding=UTF-16LE\n" % rel, encoding="utf-8"
        )
        self.git("rm", "--cached", rel)
        self.git("add", rel)
        staged = self.staged_bytes(rel)
        self.assertNotEqual(staged, disk, "fixture did not apply the encoding transformation")
        self.assert_rejected(self.run_helper(), rel)

    def test_negative_text_override_blocks_autocrlf_normalization(self):
        """-text is explicit; core.autocrlf must not make LF acceptable."""
        self.build()
        self.git("config", "core.autocrlf", "true")
        rel = BINTEXT_PATH
        disk = (self.repo / rel).read_bytes()
        self.assertIn(b"\r", disk, "fixture lost the CRLF working bytes")
        self.write_index_blob(rel, disk.replace(b"\r\n", b"\n"))
        self.assertNotEqual(
            self.staged_bytes(rel), disk,
            "fixture must stage a line-ending variant for this attack",
        )
        self.assert_rejected(self.run_helper(), rel)

    def test_text_auto_binary_content_is_not_normalized(self):
        """text=auto does not wave through NUL/binary staged bytes."""
        self.build()
        rel = TEXTAUTO_BIN_PATH
        disk = (self.repo / rel).read_bytes()
        self.assertIn(b"\0", disk, "fixture lost the binary working bytes")
        self.assertIn(b"\r", disk, "fixture lost the CRLF working bytes")
        self.write_index_blob(rel, disk.replace(b"\r\n", b"\n"))
        self.assertNotEqual(
            self.staged_bytes(rel), disk,
            "fixture must stage a binary line-ending variant",
        )
        self.assert_rejected(self.run_helper(), rel)

    def test_byte_difference_beyond_newlines_is_rejected(self):
        """Normalization covers CRLF/LF only, never spaces or other content."""
        self.build()
        rel = BYTEDIFF_PATH
        current = (self.repo / rel).read_bytes()
        self.stage_older_version(rel, b"bytediff \r\nline\r\n", current)
        self.assert_rejected(self.run_helper(), rel)

    def test_bare_carriage_return_is_not_normalized(self):
        """A lone CR is not a CRLF/LF difference and must be rejected."""
        self.build()
        rel = BYTEDIFF_PATH
        disk = (self.repo / rel).read_bytes()
        self.assertIn(b"\r", disk, "fixture lost the CRLF working bytes")
        self.write_index_blob(rel, b"bytediff\rCR\nline\n")
        self.assert_rejected(self.run_helper(), rel)

    def test_path_with_spaces_modified_staged_is_rejected(self):
        self.build()
        rel = SPACE_PATH
        current = (self.repo / rel).read_bytes()
        self.stage_older_version(rel, b"SPACED = 0\n", current)
        self.assert_rejected(self.run_helper(), rel)

    def test_stale_case_alias_governance_bytes_are_rejected(self):
        """A differently cased governance path cannot satisfy the required set
        and then escape the parity comparison (T26.corrections 2)."""
        self.build()
        self.assert_accepted(self.run_helper())

        canonical = ".ai/state.json"
        alias = ".AI/state.json"
        current = (self.repo / canonical).read_bytes()
        older_oid = self.git("rev-parse", "HEAD:" + canonical).stdout.strip()
        self.assertTrue(older_oid, "fixture could not read HEAD's state.json blob")

        # Remove only the canonical index entry and insert the older blob under
        # a differently cased spelling; the audited disk bytes stay current.
        self.git("update-index", "--force-remove", canonical)
        self.git(
            "update-index", "--add", "--cacheinfo",
            "100644,%s,%s" % (older_oid, alias),
        )
        staged = subprocess.run(
            ["git", "show", ":" + alias], cwd=str(self.repo),
            capture_output=True, timeout=60,
        ).stdout
        self.assertNotEqual(
            staged, current,
            "fixture did not stage the older governance bytes under the alias",
        )
        res = self.audit_check()
        self.assertEqual(
            res.returncode, 0,
            "the audited working tree must stay clean for this attack:\n%s\n%s"
            % (res.stdout, res.stderr),
        )

        self.assert_rejected(self.run_helper(), "state.json")

        # Canonical control: restoring the real spelling with current bytes
        # must be accepted again.
        self.git("update-index", "--force-remove", alias)
        self.git("add", canonical)
        self.assert_accepted(self.run_helper())

    def test_index_and_project_bytes_unchanged_on_reject(self):
        self.build()
        self.write("a.py", "VALUE = 99\n")
        self.git("add", "a.py")
        before_index = self.index_entries()
        before_index_bytes = self.index_file_bytes()
        before_files = snapshot_tree(self.repo)
        before_runs = (self.repo / ".ai" / "runner-runs.txt").read_bytes()

        self.assert_rejected(self.run_helper(), "a.py")

        self.assertEqual(self.index_entries(), before_index, "hook mutated the index")
        self.assertEqual(
            self.index_file_bytes(), before_index_bytes,
            "the raw index file changed while rejecting (a stat refresh is still a write)",
        )
        self.assertEqual(snapshot_tree(self.repo), before_files, "hook mutated project files")
        self.assertEqual(
            (self.repo / ".ai" / "runner-runs.txt").read_bytes(), before_runs,
            "hook executed the configured test command",
        )
        self.assertFalse(
            (self.repo / ".ai" / "AUDIT.md").exists(),
            "hook wrote an audit artifact",
        )


class TestWrapperInstallation(_CommitGateCase):
    """The shell wrapper must find its helper in documented layouts."""

    def commit(self):
        return self.git("commit", "-m", "hook run", check=False)

    def test_wrapper_integrations_layout_passes(self):
        self.build()
        shutil.copy(WRAPPER_SRC, self.repo / ".git" / "hooks" / "pre-commit")
        res = self.commit()
        self.assertEqual(
            res.returncode, 0,
            "documented integrations/ layout must commit:\n%s\n%s"
            % (res.stdout, res.stderr),
        )

    def test_wrapper_hooks_dir_sibling_helper_passes(self):
        self.build(install_helper=False)
        self.assertFalse(
            (self.repo / "integrations" / "git" / "pre_commit.py").exists(),
            "the sibling layout must not fall back to a repository helper",
        )
        hooks = self.repo / ".git" / "hooks"
        shutil.copy(WRAPPER_SRC, hooks / "pre-commit")
        shutil.copy(HOOK_SRC, hooks / "pre_commit.py")
        res = self.commit()
        self.assertEqual(
            res.returncode, 0,
            "a wrapper beside its helper must commit:\n%s\n%s"
            % (res.stdout, res.stderr),
        )

    def test_wrapper_integrations_layout_rejects_stale_bytes(self):
        """A real git commit must be rejected when the wrapper runs from
        .git/hooks but the helper lives in integrations/git."""
        self.build()
        before_head = self.git("rev-parse", "HEAD").stdout.strip()
        before_runs = (self.repo / ".ai" / "runner-runs.txt").read_bytes()
        self.write("a.py", "VALUE = 99\n")
        self.git("add", "a.py")
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        shutil.copy(WRAPPER_SRC, hooks / "pre-commit")

        res = self.commit()
        out = (res.stdout or "") + (res.stderr or "")
        self.assertNotEqual(
            res.returncode, 0,
            "a stale artifact must not commit through the integrations layout:\n%s" % out,
        )
        self.assertIn("PRE-COMMIT ERROR", out, "wrapper did not run the helper:\n%s" % out)
        self.assertIn("a.py", out, "rejection must name the stale artifact:\n%s" % out)
        self.assertEqual(
            self.git("rev-parse", "HEAD").stdout.strip(), before_head,
            "a rejected commit changed HEAD",
        )
        self.assertEqual(
            (self.repo / ".ai" / "runner-runs.txt").read_bytes(), before_runs,
            "the hook executed the configured test command",
        )

    def test_wrapper_hooks_dir_sibling_helper_rejects_stale_bytes(self):
        """The copied-pair layout must reject stale bytes after the wrapper
        changes into its own directory to resolve the helper."""
        self.build(install_helper=False)
        self.assertFalse(
            (self.repo / "integrations" / "git" / "pre_commit.py").exists(),
            "the sibling layout must not fall back to a repository helper",
        )
        hooks = self.repo / ".git" / "hooks"
        shutil.copy(WRAPPER_SRC, hooks / "pre-commit")
        shutil.copy(HOOK_SRC, hooks / "pre_commit.py")
        before_head = self.git("rev-parse", "HEAD").stdout.strip()
        before_runs = (self.repo / ".ai" / "runner-runs.txt").read_bytes()
        self.write("a.py", "VALUE = 99\n")
        self.git("add", "a.py")

        res = self.commit()
        out = (res.stdout or "") + (res.stderr or "")
        self.assertNotEqual(
            res.returncode, 0,
            "a stale artifact must not commit through the copied-pair layout:\n%s" % out,
        )
        self.assertIn("PRE-COMMIT ERROR", out, "wrapper did not run its sibling helper:\n%s" % out)
        self.assertIn("a.py", out, "rejection must name the stale artifact:\n%s" % out)
        self.assertEqual(
            self.git("rev-parse", "HEAD").stdout.strip(), before_head,
            "a rejected commit changed HEAD",
        )
        self.assertEqual(
            (self.repo / ".ai" / "runner-runs.txt").read_bytes(), before_runs,
            "the hook executed the configured test command",
        )

    def test_wrapper_unsupported_layout_fails_clearly(self):
        logger = self.repo / "app.py"
        logger.write_text("VALUE = 1\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-m", "baseline")
        hooks = self.repo / ".git" / "hooks"
        shutil.copy(WRAPPER_SRC, hooks / "pre-commit")
        self.git("add", "-A", check=False)
        res = self.commit()
        out = (res.stdout or "") + (res.stderr or "")
        self.assertNotEqual(res.returncode, 0, "a wrapper with no helper must not commit:\n%s" % out)
        self.assertIn("pre_commit.py", out, "failure must name the helper it could not locate:\n%s" % out)


if __name__ == "__main__":
    unittest.main()
