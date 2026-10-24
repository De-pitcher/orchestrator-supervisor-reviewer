import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OSR = str(ROOT_DIR / "scripts" / "osr.py")


class TestProject:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="osr-test-honest-"))
        self.write("src/__init__.py", "")
        self.write("tests/__init__.py", "")
        self.write("tests/test_base.py", (
            "import unittest\n"
            "class B(unittest.TestCase):\n"
            "    def test_b(self):\n"
            "        self.assertTrue(True)\n"
        ))

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel):
        return (self.dir / rel).read_text(encoding="utf-8")

    def osr(self, *args):
        r = subprocess.run([sys.executable, OSR, "--root", str(self.dir)] + list(args), capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr


class TestHonestReporting(unittest.TestCase):
    def setUp(self):
        self.p = TestProject()
        self.addCleanup(self.p.cleanup)

    # R6 Acceptance Test: Heuristic warnings are explicitly labeled as heuristics,
    # CI matrix includes Python 3.8, and README/CHANGELOG report honest denominators.
    def test_honest_reporting_and_heuristics(self):
        p = self.p

        # 1. Check CI matrix includes Python 3.8
        workflow_p = ROOT_DIR / ".github" / "workflows" / "test.yml"
        self.assertTrue(workflow_p.exists(), ".github/workflows/test.yml must exist")
        workflow_text = workflow_p.read_text(encoding="utf-8")
        self.assertIn('"3.8"', workflow_text, "CI matrix must explicitly include Python 3.8")

        # 2. Check plan-check heuristic warning is explicitly labeled as heuristic
        p.osr("init")
        plan_heuristic = """# Plan
## Goal
Test heuristic warning.
## Non-goals
None.
## Requirements
- R1: Connect to external user service API endpoint
  - AC: fetches user details over HTTP REST endpoint successfully
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
        p.write(".ai/PLAN.md", plan_heuristic)
        code, out = p.osr("plan-check")
        self.assertIn("heuristic", out.lower(), f"plan-check seam warning must be explicitly labeled as heuristic: {out}")

        # 3. Check README and CHANGELOG do not claim misleading 100% (10/10) denominator
        readme_text = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("100% (10/10 active vectors caught)", readme_text,
                         "README must use honest denominators rather than 100% (10/10 active vectors caught)")
        self.assertIn("12", readme_text, "README must cite full vector denominator (12 vectors)")

        changelog_text = (ROOT_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("0.3.1", changelog_text, "CHANGELOG must document v0.3.1 release")
        self.assertIn("known limitations", changelog_text.lower(), "CHANGELOG must include a Known limitations section")


if __name__ == "__main__":
    unittest.main()
