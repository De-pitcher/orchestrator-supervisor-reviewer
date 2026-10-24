import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL_SCRIPT = ROOT / "scripts" / "sync_skill.py"

# Explicit synced file set (decision record): these, and only these, are synced.
SYNCED_FILES = ["SKILL.md", "PROMPT-ONLY.md", "README.md", "CHANGELOG.md", "LICENSE"]
SYNCED_DIRS = ["scripts", "assets", "references", "integrations", "tests", "evals", "examples"]
# Explicitly NOT synced.
NOT_SYNCED = [".github/workflows/test.yml", "docs/vendor/notes.md", ".gitignore", "CONTRIBUTING.md", "pyproject.toml"]
# Excluded directory names inside synced items.
EXCLUDED_DIR_NAMES = [".git", ".ai", "__pycache__"]


def make_repo(base):
    """Create a hermetic fake repo root containing a copy of sync_skill.py; return (repo_root, script_path)."""
    repo = Path(base) / "repo"
    for f in SYNCED_FILES:
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text("content of " + f, encoding="utf-8")
    for d in SYNCED_DIRS:
        (repo / d).mkdir(parents=True, exist_ok=True)
        (repo / d / ("sample_" + d + ".txt")).write_text("sample in " + d, encoding="utf-8")
    for f in NOT_SYNCED:
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text("not synced " + f, encoding="utf-8")
    (repo / "scripts" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "__pycache__" / "junk.txt").write_text("junk", encoding="utf-8")
    (repo / "scripts" / ".ai").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / ".ai" / "state.txt").write_text("state", encoding="utf-8")
    script = repo / "scripts" / "sync_skill.py"
    if REAL_SCRIPT.is_file():
        shutil.copy2(REAL_SCRIPT, script)
    return repo, script


def run(script, *args, cwd=None):
    return subprocess.run(
        [sys.executable, str(script)] + [str(a) for a in args],
        capture_output=True, text=True, cwd=str(cwd or script.parent.parent),
    )


class SyncSkillTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def synced_target(self, repo_script_pair=None):
        repo, script = repo_script_pair or make_repo(self.base)
        target = self.base / "target_skill"
        proc = run(script, "--target", target)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return repo, script, target

    def test_sync_skill_script_exists(self):
        self.assertTrue(REAL_SCRIPT.is_file(), "scripts/sync_skill.py must exist")

    def test_sync_skill_real_repo_sync_and_check_smoke(self):
        target = self.base / "real_target"
        proc = run(REAL_SCRIPT, "--target", target)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertTrue((target / "scripts" / "osr.py").is_file())
        chk = run(REAL_SCRIPT, "--check", "--target", target)
        self.assertEqual(chk.returncode, 0, chk.stderr + chk.stdout)

    def test_sync_skill_file_set_included_and_excluded(self):
        repo, script, target = self.synced_target()
        for f in SYNCED_FILES:
            self.assertTrue((target / f).is_file(), "expected synced file " + f)
        for d in SYNCED_DIRS:
            self.assertTrue((target / d / ("sample_" + d + ".txt")).is_file(), "expected synced dir " + d)
        for f in NOT_SYNCED:
            self.assertFalse((target / f).exists(), "must NOT sync " + f)
        for name in EXCLUDED_DIR_NAMES:
            self.assertFalse((target / "scripts" / name).exists(), "excluded dir leaked: " + name)
        chk = run(script, "--check", "--target", target)
        self.assertEqual(chk.returncode, 0, chk.stderr + chk.stdout)

    def test_sync_skill_negative_differing_file(self):
        repo, script, target = self.synced_target()
        (target / "SKILL.md").write_text("tampered content", encoding="utf-8")
        proc = run(script, "--check", "--target", target)
        out = proc.stderr + proc.stdout
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("differs", out)
        self.assertIn("SKILL.md", out)

    def test_sync_skill_negative_missing_file(self):
        repo, script, target = self.synced_target()
        (target / "SKILL.md").unlink()
        proc = run(script, "--check", "--target", target)
        out = proc.stderr + proc.stdout
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("missing", out.lower())
        self.assertIn("SKILL.md", out)

    def test_sync_skill_negative_extra_file_inside_synced_item(self):
        repo, script, target = self.synced_target()
        (target / "scripts" / "extra_untracked.txt").write_text("unexpected", encoding="utf-8")
        proc = run(script, "--check", "--target", target)
        out = proc.stderr + proc.stdout
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("extra", out.lower())
        self.assertIn("extra_untracked.txt", out)

    def test_sync_skill_extra_outside_synced_items_not_flagged(self):
        repo, script, target = self.synced_target()
        (target / "unrelated_root_file.txt").write_text("not ours", encoding="utf-8")
        (target / "docs").mkdir(exist_ok=True)
        (target / "docs" / "local_notes.md").write_text("not ours", encoding="utf-8")
        proc = run(script, "--check", "--target", target)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)

    def test_sync_skill_excludes_use_root_relative_paths(self):
        # Repo and target both live under parent folders named "venv" and ".ai".
        deep = self.base / "venv" / ".ai"
        deep.mkdir(parents=True)
        repo, script = make_repo(deep)
        target = deep / "venv" / "target_skill"
        proc = run(script, "--target", target)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue((target / "SKILL.md").is_file(), "SKILL.md must sync even under venv/.ai parents")
        self.assertTrue((target / "scripts" / "sample_scripts.txt").is_file(), "scripts/ content must sync")
        self.assertFalse((target / "scripts" / "__pycache__").exists(), "excluded dir must still be excluded")
        chk = run(script, "--check", "--target", target)
        self.assertEqual(chk.returncode, 0, chk.stderr + chk.stdout)

    def test_sync_skill_sync_without_prune_keeps_extras(self):
        repo, script, target = self.synced_target()
        extra = target / "scripts" / "stale_extra.txt"
        extra.write_text("stale", encoding="utf-8")
        proc = run(script, "--target", target)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertTrue(extra.exists(), "extras must be kept unless --prune is passed")

    def test_sync_skill_prune_removes_extras_inside_synced_items_only(self):
        repo, script, target = self.synced_target()
        inside = target / "scripts" / "stale_extra.txt"
        outside = target / "unrelated_root_file.txt"
        inside.write_text("stale", encoding="utf-8")
        outside.write_text("keep me", encoding="utf-8")
        proc = run(script, "--target", target, "--prune")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertFalse(inside.exists(), "--prune must remove extras inside synced items")
        self.assertIn("stale_extra.txt", proc.stdout + proc.stderr, "prune must name what it removed")
        self.assertTrue(outside.exists(), "--prune must not touch files outside synced items")
        chk = run(script, "--check", "--target", target)
        self.assertEqual(chk.returncode, 0, chk.stderr + chk.stdout)

    def test_sync_skill_prune_with_check_is_rejected(self):
        repo, script, target = self.synced_target()
        proc = run(script, "--check", "--prune", "--target", target)
        out = proc.stderr + proc.stdout
        self.assertNotEqual(proc.returncode, 0, out)
        self.assertIn("--prune", out)
        self.assertNotIn("unrecognized arguments", out)

    def test_sync_skill_sync_mode_requires_target(self):
        import os
        repo, script = make_repo(self.base)
        fake_home = self.base / "fake_home"
        env = dict(os.environ, HOME=str(fake_home), USERPROFILE=str(fake_home))
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, cwd=str(repo), env=env,
        )
        out = proc.stderr + proc.stdout
        self.assertNotEqual(proc.returncode, 0, out)
        self.assertIn("--target", out)
        self.assertFalse(fake_home.exists(), "sync without --target must not write to default home path")


if __name__ == "__main__":
    unittest.main()
