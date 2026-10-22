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
        self.dir = Path(tempfile.mkdtemp(prefix="osr-test-fix-"))
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

    def setup_ready(self, approve=True, plan=None, card=None):
        code, out = self.osr("init")
        assert code == 0, out
        cfg = json.loads(self.read(".ai/config.json"))
        py = sys.executable
        cfg["commands"] = {
            "test": {"cmd": f'"{py}" -m unittest discover -s tests -t . -q', "verified": False},
            "capture_provider": {"cmd": f'"{py}" -c "print(12345)"', "verified": False},
            "conformance_cmd": {"cmd": f'"{py}" -c "import sys; sys.exit(0)"', "verified": False}
        }
        cfg["global_verify"] = ["test"]
        self.write(".ai/config.json", json.dumps(cfg))
        code, out = self.osr("confirm-commands")
        assert code == 0 and "CONFIRMED" in out, out
        if plan:
            self.write(".ai/PLAN.md", plan)
        if card:
            self.write(".ai/tasks/T1.md", card)
        if approve:
            code, out = self.osr("approve-plan", "--by", "human")
            assert code == 0, out


class TestFixtureCaptureAndSeams(unittest.TestCase):
    def setUp(self):
        self.p = TestProject()
        self.addCleanup(self.p.cleanup)

    # R2 Acceptance Test: osr fixture-capture executes confirmed commands recording stdout,
    # seam cards with fixtures mandate conformance commands or report unverified,
    # and seam sources in test/mock paths are rejected.
    def test_fixture_capture_and_seam_source(self):
        p = self.p

        # Part 1: Bogus seam source in test/mock path must be rejected by plan-check & task-check
        bogus_plan = """# Plan
## Goal
Test seam source rejection.
## Non-goals
None.
## Requirements
- R1: User format
  - AC: formats user from provider [test_user]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | tests/mocks/fake_user_service.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
        p.write("tests/mocks/fake_user_service.py", "# Fake mock provider\n")
        p.write(".ai/PLAN.md", bogus_plan)
        code, out = p.osr("init")
        self.assertEqual(code, 0)
        code, out = p.osr("plan-check")
        self.assertNotEqual(code, 0, "plan-check must reject seam authoritative source in test/mock path")
        self.assertIn("authoritative source", out.lower())

        # Now fix plan with legitimate authoritative provider source
        valid_plan = """# Plan
## Goal
Test seam capture and conformance.
## Non-goals
None.
## Requirements
- R1: User format
  - AC: formats user from provider [test_user]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | services/user_service.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
        p.write("services/user_service.py", "# Real service provider\n")
        p.write(".ai/PLAN.md", valid_plan)
        code, out = p.osr("plan-check")
        self.assertEqual(code, 0, f"plan-check should pass with valid source: {out}")

        # Part 2: approve-plan displays Seams table
        cfg = json.loads(p.read(".ai/config.json"))
        py = sys.executable
        cfg["commands"] = {
            "test": {"cmd": f'"{py}" -m unittest discover -s tests -t . -q', "verified": False},
            "capture_provider": {"cmd": f'"{py}" -c "print(12345)"', "verified": False},
            "conformance_cmd": {"cmd": f'"{py}" -c "import sys; sys.exit(0)"', "verified": False}
        }
        cfg["global_verify"] = ["test"]
        p.write(".ai/config.json", json.dumps(cfg))
        code, out = p.osr("confirm-commands")
        self.assertEqual(code, 0)
        code, out = p.osr("approve-plan", "--by", "human")
        self.assertEqual(code, 0)
        self.assertIn("user_api", out, "approve-plan must prominently display declared seams")
        self.assertIn("services/user_service.py", out)

        # Part 3: Mandatory conformance on seam cards that declare fixtures
        test_cmd = f'"{py}" -m unittest discover -s tests -t . -q'
        card_without_conformance = f"""# T1: User Task
id: T1
requirements: R1
seams: user_api
fixtures: fixtures/user.json
allowed_files: src/user.py, tests/test_user.py
context_files: .ai/PLAN.md, services/user_service.py
verify: {test_cmd}

## Goal
Test user.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
        p.write(".ai/tasks/T1.md", card_without_conformance)
        code, out = p.osr("task-check", "T1")
        self.assertIn("conformance", out.lower(), "task-check must warn when a seam card with fixtures lacks conformance commands")

        # Part 4: Tool-captured fixture with confirmed command
        # Unconfirmed command should fail
        code, out = p.osr("fixture-capture", "fixtures/user.json", "--seam", "user_api", "--cmd", "unconfirmed_capture_cmd")
        self.assertNotEqual(code, 0, "fixture-capture with unconfirmed command must fail")

        # Confirmed capture command executes, writes fixture file, and records provenance
        code, out = p.osr("fixture-capture", "fixtures/user.json", "--seam", "user_api", "--cmd", "capture_provider")
        self.assertEqual(code, 0, f"fixture-capture must succeed: {out}")
        self.assertTrue((p.dir / "fixtures/user.json").is_file(), "Fixture file must be written")
        fixture_content = p.read("fixtures/user.json")
        self.assertIn("12345", fixture_content)

        state = json.loads(p.read(".ai/state.json"))
        fix_meta = state.get("fixtures", {}).get("fixtures/user.json")
        self.assertIsNotNone(fix_meta)
        self.assertEqual(fix_meta.get("cmd"), "capture_provider")
        self.assertIn("sha256", fix_meta)

        # Card with conformance now passes task-check
        card_with_conformance = f"""# T1: User Task
id: T1
requirements: R1
seams: user_api
fixtures: fixtures/user.json
conformance: conformance_cmd
allowed_files: src/user.py, tests/test_user.py
context_files: .ai/PLAN.md, services/user_service.py
verify: {test_cmd}

## Goal
Test user.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
        p.write(".ai/tasks/T1.md", card_with_conformance)
        code, out = p.osr("task-check", "T1")
        self.assertEqual(code, 0, f"task-check should pass when conformance is specified: {out}")


if __name__ == "__main__":
    unittest.main()
