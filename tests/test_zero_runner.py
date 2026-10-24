import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OSR = str(Path(__file__).resolve().parent.parent / "scripts" / "osr.py")


class TestProject:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="osr-test-zero-"))
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

    def setup_ready(self, plan_text, card_text, baseline=None, extra_commands=None):
        self.osr("init")
        py = sys.executable
        cfg = json.loads(self.read(".ai/config.json"))
        commands = {
            "test": {"cmd": f'"{py}" -m unittest discover -s tests -t . -q', "verified": False},
        }
        for name, cmd in (extra_commands or {}).items():
            commands[name] = {"cmd": cmd, "verified": False}
        cfg["commands"] = commands
        cfg["global_verify"] = ["test"]
        self.write(".ai/config.json", json.dumps(cfg))
        for rel, text in (baseline or {}).items():
            self.write(rel, text)
        self.osr("confirm-commands")
        self.write(".ai/PLAN.md", plan_text)
        self.write(".ai/tasks/T1.md", card_text)
        self.osr("approve-plan", "--by", "human")


class TestZeroRunner(unittest.TestCase):
    def setUp(self):
        self.p = TestProject()
        self.addCleanup(self.p.cleanup)

    # R3 Acceptance Test: osr verify parses test runner stdout and fails with exit code 1
    # when zero tests are collected or executed, and catches weak grep/token verify commands (V12).
    def test_verify_zero_tests_rejected(self):
        p = self.p
        py = sys.executable

        plan = """# Plan
## Goal
Test zero runner detection.
## Non-goals
None.
## Requirements
- R1: Add functionality
  - AC: calculation adds two numbers correctly [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""

        # Part 1: Verify command that executes 0 tests after start. The same
        # focused loader genuinely runs one real test during confirmation and
        # start; only the post-start fixture module becomes invisible to the
        # loader, while the test function and its assertions remain present.
        zero_verify_cmd = f'"{py}" -m unittest discover -s tests -p test_calc.py -v'
        card_zero_tests = f"""# T1: Add
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: {zero_verify_cmd}

## Goal
Add two numbers.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
        p.setup_ready(
            plan,
            card_zero_tests,
            baseline={
                "src/calc.py": "def add(a, b): return a + b\n",
                "tests/test_calc.py": (
                    "import unittest\n"
                    "from src.calc import add\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_add(self): self.assertEqual(add(2, 3), 5)\n"
                ),
            },
            extra_commands={"focused": zero_verify_cmd},
        )
        code, out = p.osr("start", "T1")
        self.assertEqual(code, 0, out)
        p.write("src/calc.py", "def add(a, b): return a + b\n")
        p.write("tests/test_calc.py", "import unittest\nfrom src.calc import add\nclass LoaderInvisible:\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n")
        code, out = p.osr("verify", "T1")
        self.assertNotEqual(code, 0, f"verify must fail when runner executes 0 tests: {out}")
        self.assertIn("no tests ran", out.lower())
        self.assertIn("weak verify command", out.lower())

        # Part 2: Weak grep-style verify command that tests token existence instead of behavior
        weak_grep_cmd = f'"{py}" -c "import sys, pathlib; sys.exit(0 if \'def add\' in pathlib.Path(\'src/calc.py\').read_text() else 1)"'
        card_weak_grep = f"""# T1: Add
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: {weak_grep_cmd}

## Goal
Add two numbers.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
        p.write(".ai/tasks/T1.md", card_weak_grep)
        code, out = p.osr("task-check", "T1")
        self.assertNotEqual(code, 0, "task-check must reject token existence check / weak verify command")
        self.assertIn("weak verify command", out.lower())


if __name__ == "__main__":
    unittest.main()
