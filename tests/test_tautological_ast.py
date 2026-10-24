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
        self.dir = Path(tempfile.mkdtemp(prefix="osr-test-tautology-"))
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

    def setup_ready(self, plan_text, card_text):
        self.osr("init")
        py = sys.executable
        cfg = json.loads(self.read(".ai/config.json"))
        cfg["commands"] = {
            "test": {"cmd": f'"{py}" -m unittest discover -s tests -t . -q', "verified": False},
            "card": {"cmd": f'"{py}" -m unittest tests.test_calc -v', "verified": False},
        }
        cfg["global_verify"] = ["test"]
        self.write(".ai/config.json", json.dumps(cfg))
        # The exact card verify command must really run a passing baseline
        # during confirmation; the cheat scenarios still change these bytes
        # only after start.
        self.write("src/calc.py", "def add(a, b):\n    return a + b\n")
        self.write("tests/test_calc.py", (
            "import unittest\n"
            "from src.calc import add\n"
            "class T(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(add(2, 3), 5)\n"
            "        self.assertEqual(add(-1, 1), 0)\n"
            "        self.assertEqual(add(0, 0), 0)\n"
        ))
        code, out = self.osr("confirm-commands")
        assert code == 0, out
        assert "=> card: CONFIRMED" in out, out
        self.write(".ai/PLAN.md", plan_text)
        self.write(".ai/tasks/T1.md", card_text)
        self.osr("approve-plan", "--by", "human")


class TestTautologicalAst(unittest.TestCase):
    def setUp(self):
        self.p = TestProject()
        self.addCleanup(self.p.cleanup)

    # R4 Acceptance Test: osr check inspects Python AST for constant assertions and self-comparisons
    # and flags JavaScript expect self-match regex [test_tautological_assertion_ast]
    def test_tautological_assertion_ast(self):
        p = self.p
        py = sys.executable

        plan = """# Plan
## Goal
Test tautological assertion detection.
## Non-goals
None.
## Requirements
- R1: Math add
  - AC: add returns sum [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
        card = f"""# T1: Add
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py, tests/test_widget.js
context_files: .ai/PLAN.md
verify: "{py}" -m unittest tests.test_calc -v

## Goal
Add numbers.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
        p.setup_ready(plan, card)
        code, out = p.osr("start", "T1")
        self.assertEqual(code, 0, out)

        # Case 1: Python constant assertion: assert 1 == 1 and assert True
        p.write("src/calc.py", "def add(a, b): return 'wrong'\n")
        p.write("tests/test_calc.py", (
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        assert 1 == 1\n"
            "        self.assertEqual(x, x)\n"
            "        self.assertTrue(True)\n"
        ))

        code, out = p.osr("check", "T1")
        self.assertNotEqual(code, 0, "osr check must fail when tautological Python assertions are present")
        self.assertIn("tautological-assertion", out.lower(), f"Expected tautological-assertion flag in output: {out}")

        # Case 2: JavaScript self-match expect: expect(x).toBe(x)
        p.write("tests/test_calc.py", (
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        self.assertEqual(1 + 1, 2)\n"
        ))
        p.write("tests/test_widget.js", (
            "test('widget', () => {\n"
            "  expect(widget).toBe(widget);\n"
            "});\n"
        ))

        code, out = p.osr("check", "T1")
        self.assertNotEqual(code, 0, "osr check must fail when tautological JS assertions are present")
        self.assertIn("tautological-assertion", out.lower(), f"Expected tautological-assertion flag in output: {out}")


if __name__ == "__main__":
    unittest.main()
