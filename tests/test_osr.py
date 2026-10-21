"""End-to-end tests for osr.py. Run:  python -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OSR = str(Path(__file__).resolve().parent.parent / "scripts" / "osr.py")

PLAN = """# Plan: calc

## Goal
Add an add() function.

## Non-goals
- No command line interface.

## Requirements
- R1: add returns the sum of two ints
  - AC: add(2,3) returns 5 and add(-1,1) returns 0
  - Check: auto
- R2: wording of the module docstring is friendly
  - AC: a human reads the docstring and finds it friendly
  - Check: manual

## Assumptions
- [x] Python 3 only

## Open questions
"""

CARD = """# T1: add function
id: T1
requirements: R1, R2
depends_on:
allowed_files: src/calc.py, tests/test_calc.py
context_files:
verify: "%s" -m unittest tests.test_calc -q

## Goal
Implement add(a, b) in src/calc.py with tests.

## Constraints
- Python 3 standard library only.

## Do not
- Do not touch other files.

## Definition of done
- add(2,3) == 5 and tests pass.
""" % sys.executable

GOOD_CODE = '"""Friendly calculator."""\ndef add(a, b):\n    return a + b\n'
GOOD_TEST = (
    "import unittest\nfrom src.calc import add\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertEqual(add(2, 3), 5)\n"
    "        self.assertEqual(add(-1, 1), 0)\n"
)
SPEC_OK = 'R1: PASS @ src/calc.py:3 "return a + b"\nR2: UNVERIFIED - a human must judge the docstring tone\n\nVERDICT: PASS\n'
QUALITY_OK = """C1: PASS - no imports in the changed file, nothing to resolve
C2: PASS - ints only per the plan, no edge handling required
C3: NA - no input handling or secrets involved
C4: PASS - no stubs or placeholder markers present
C5: PASS - no other callers exist in the repository
C6: PASS - test asserts two exact sums, no skips present
C7: PASS - style matches the tiny existing package
C8: PASS - only the two allowed files changed

BREAK_ATTEMPTS:
- Pass floats and check that rounding errors are acceptable per the plan
- Pass very large ints and confirm no overflow in Python ints
- Pass strings and observe whether it concatenates instead of failing

VERDICT: PASS
"""


class Project:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="osr-test-"))
        self.write("src/__init__.py", "")
        self.write("tests/__init__.py", "")
        self.write("tests/test_base.py", "import unittest\nclass B(unittest.TestCase):\n    def test_b(self):\n        self.assertEqual(1, 1)\n")

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel):
        return (self.dir / rel).read_text(encoding="utf-8")

    def osr(self, *args):
        r = subprocess.run([sys.executable, OSR, "--root", str(self.dir)] + list(args), capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def setup_ready(self, approve=True):
        assert self.osr("init")[0] == 0
        cfg = json.loads(self.read(".ai/config.json"))
        cfg["commands"] = {"test": {"cmd": '"%s" -m unittest discover -s tests -t . -q' % sys.executable, "verified": False}}
        cfg["global_verify"] = ["test"]
        self.write(".ai/config.json", json.dumps(cfg))
        code, out = self.osr("confirm-commands")
        assert code == 0 and "CONFIRMED" in out, out
        self.write(".ai/PLAN.md", PLAN)
        self.write(".ai/tasks/T1.md", CARD)
        if approve:
            code, out = self.osr("approve-plan", "--by", "human")
            assert code == 0, out

    def implement(self):
        self.write("src/calc.py", GOOD_CODE)
        self.write("tests/test_calc.py", GOOD_TEST)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class OsrTests(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.cleanup)

    def test_full_happy_path(self):
        p = self.p
        p.setup_ready()
        self.assertEqual(p.osr("task-check", "--all")[0], 0)
        code, out = p.osr("start", "T1", "--model", "model-a")
        self.assertEqual(code, 0, out)
        p.implement()
        code, out = p.osr("verify", "T1")
        self.assertEqual(code, 0, out)
        p.write(".ai/reviews/T1.spec.md", SPEC_OK)
        code, out = p.osr("review", "T1", "spec", "--reviewer", "model-b")
        self.assertEqual(code, 0, out)
        p.write(".ai/reviews/T1.quality.md", QUALITY_OK)
        code, out = p.osr("review", "T1", "quality", "--reviewer", "model-b")
        self.assertEqual(code, 0, out)
        code, out = p.osr("done", "T1")
        self.assertEqual(code, 0, out)
        code, out = p.osr("audit")
        self.assertEqual(code, 2, out)  # R2 is manual -> pending human
        self.assertIn("PENDING-HUMAN", out)
        self.assertIn("VERIFIED", out)
        self.assertEqual(p.osr("signoff", "R2", "--by", "human", "--note", "read it")[0], 0)
        code, out = p.osr("audit")
        self.assertEqual(code, 0, out)

    def test_plan_must_be_approved_and_stay_unchanged(self):
        p = self.p
        p.setup_ready(approve=False)
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertNotEqual(code, 0)
        self.assertIn("not approved", out)
        p.osr("approve-plan", "--by", "human")
        p.write(".ai/PLAN.md", PLAN + "\n- tweak\n")
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertNotEqual(code, 0)
        self.assertIn("changed since approval", out)

    def test_unconfirmed_commands_block_approval(self):
        p = self.p
        p.osr("init")
        p.write(".ai/PLAN.md", PLAN)
        code, out = p.osr("approve-plan", "--by", "human")
        self.assertNotEqual(code, 0)
        self.assertIn("confirmed", out)

    def test_scope_violation_blocks_verify(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        p.implement()
        p.write("src/other.py", "x = 1\n")
        code, out = p.osr("verify", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("SCOPE VIOLATION", out)
        self.assertIn("src/other.py", out)

    def test_placeholder_and_hallucinated_import_are_caught(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        p.write("src/calc.py", "import totally_made_up_pkg\ndef add(a, b):\n    # rest of the code unchanged\n    return a + b\n")
        p.write("tests/test_calc.py", GOOD_TEST)
        code, out = p.osr("check", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("UNRESOLVED REFERENCE", out)
        self.assertIn("placeholder:", out)

    def test_no_tests_ran_is_failure(self):
        p = self.p
        p.setup_ready()
        card = CARD.replace("tests.test_calc -q", "discover -s nonexistent_dir -q")
        p.write(".ai/tasks/T1.md", card)
        p.osr("start", "T1", "--model", "m")
        p.implement()
        code, out = p.osr("verify", "T1")
        self.assertNotEqual(code, 0)

    def test_fabricated_review_evidence_is_rejected(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        p.implement()
        self.assertEqual(p.osr("verify", "T1")[0], 0)
        p.write(".ai/reviews/T1.spec.md", 'R1: PASS @ src/calc.py:3 "return a * b"\nR2: UNVERIFIED - human judges the tone\n\nVERDICT: PASS\n')
        code, out = p.osr("review", "T1", "spec", "--reviewer", "b")
        self.assertNotEqual(code, 0)
        self.assertIn("snippet not found", out)

    def test_manual_requirement_cannot_pass(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        p.implement()
        p.osr("verify", "T1")
        p.write(".ai/reviews/T1.spec.md", 'R1: PASS @ src/calc.py:3 "return a + b"\nR2: PASS @ src/calc.py:1 "Friendly calculator."\n\nVERDICT: PASS\n')
        code, out = p.osr("review", "T1", "spec", "--reviewer", "b")
        self.assertNotEqual(code, 0)
        self.assertIn("Check: manual", out)

    def test_review_on_stale_code_and_done_gate(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        p.implement()
        p.osr("verify", "T1")
        p.write(".ai/reviews/T1.spec.md", SPEC_OK)
        self.assertEqual(p.osr("review", "T1", "spec", "--reviewer", "b")[0], 0)
        p.write("src/calc.py", GOOD_CODE + "# changed after review\n")
        code, out = p.osr("done", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("NOT DONE", out)
        code, out = p.osr("review", "T1", "quality", "--reviewer", "b")
        self.assertNotEqual(code, 0)  # code changed since verify

    def test_blind_retry_is_blocked_and_triage_forces_a_change(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        p.write("src/calc.py", "def add(a, b):\n    return a - b\n")  # wrong on purpose
        p.write("tests/test_calc.py", GOOD_TEST)
        self.assertNotEqual(p.osr("verify", "T1")[0], 0)
        self.assertNotEqual(p.osr("verify", "T1")[0], 0)
        code, out = p.osr("verify", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("Blind retries are blocked", out)
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertNotEqual(code, 0)
        self.assertIn("no diagnosis", out)
        code, out = p.osr("triage", "T1", "--layer", "prompt", "--evidence", "card never said which operator to use", "--change", "card now has an example showing add(2,3)==5")
        self.assertEqual(code, 0, out)
        code, out = p.osr("verify", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("new attempt", out)
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertNotEqual(code, 0)
        self.assertIn("unchanged", out)
        p.write(".ai/tasks/T1.md", CARD.replace("## Constraints", "## Example\nadd(2, 3) == 5\n\n## Constraints"))
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertEqual(code, 0, out)
        p.write("src/calc.py", GOOD_CODE)
        self.assertEqual(p.osr("verify", "T1")[0], 0)

    def test_spec_triage_blocks_until_human_unblocks(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "m")
        code, out = p.osr("triage", "T1", "--layer", "spec", "--evidence", "AC contradicts R2 about wording", "--change", "human clarifies the requirement")
        self.assertEqual(code, 0, out)
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertNotEqual(code, 0)
        self.assertIn("blocked", out.lower())
        self.assertEqual(p.osr("unblock", "T1", "--by", "human", "--note", "clarified").__getitem__(0), 0)
        self.assertEqual(p.osr("start", "T1", "--model", "m")[0], 0)

    def test_ledger_tampering_is_detected(self):
        p = self.p
        p.setup_ready()
        led = p.read(".ai/ledger.jsonl").replace('"ok": true', '"ok": false', 1)
        p.write(".ai/ledger.jsonl", led)
        code, out = p.osr("next")
        self.assertNotEqual(code, 0)
        self.assertIn("LEDGER INTEGRITY FAILURE", out)

    def test_waiver_rules(self):
        p = self.p
        p.setup_ready()
        code, out = p.osr("waive", "T1", "--flag", "tests-weakened:x", "--reason", "removing an obsolete assertion")
        self.assertNotEqual(code, 0)
        self.assertIn("human approval", out)
        code, out = p.osr("waive", "T1", "--flag", "tests-weakened:x", "--reason", "removing an obsolete assertion", "--approved-by", "human")
        self.assertEqual(code, 0, out)

    def test_js_references_and_weakened_tests_are_flagged(self):
        p = self.p
        p.setup_ready()
        p.write("src/calc.py", GOOD_CODE)
        p.write("tests/test_calc.py", GOOD_TEST)
        p.write(".ai/tasks/T1.md", CARD.replace("allowed_files: src/calc.py, tests/test_calc.py", "allowed_files: src/**, tests/**, package.json"))
        self.assertEqual(p.osr("start", "T1", "--model", "m")[0], 0)
        p.write("tests/test_calc.py", GOOD_TEST.replace("        self.assertEqual(add(-1, 1), 0)\n", ""))
        p.write("package.json", json.dumps({"dependencies": {"react": "18"}}))
        p.write("src/app.ts", "import React from 'react'\nimport x from 'lodash'\nimport y from './nothere'\nimport fs from 'fs'\n")
        code, out = p.osr("check", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("package 'lodash' is not declared", out)
        self.assertIn("'./nothere' does not resolve", out)
        self.assertNotIn("'react'", out)
        self.assertNotIn("'fs'", out)
        self.assertIn("tests-weakened:tests/test_calc.py:2->1", out)

    def test_next_walks_the_workflow(self):
        p = self.p
        p.osr("init")
        self.assertIn("detect", p.osr("next")[1])
        p.setup_ready(approve=False)
        self.assertIn("approve-plan", p.osr("next")[1])
        p.osr("approve-plan", "--by", "human")
        self.assertIn("start T1", p.osr("next")[1])
        p.osr("start", "T1", "--model", "m")
        self.assertIn("verify T1", p.osr("next")[1])

    def test_json_output_and_exit_codes(self):
        p = self.p
        p.setup_ready()
        # Test osr next with --json
        code, out = p.osr("next", "--json")
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        self.assertTrue(data.get("ok"))
        self.assertIn("action", data)
        self.assertEqual(data["action"], "osr start T1 --model <your-model-name>")

        # Test gate rejection with --json: verify before implementing returns exit code 2
        p.osr("start", "T1", "--model", "m")
        code, out = p.osr("verify", "T1", "--json")
        self.assertEqual(code, 2, "Gate failure should return exit code 2")
        data = json.loads(out)
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("exit_code"), 2)

    def test_ledger_locking_concurrency(self):
        p = self.p
        p.setup_ready()
        lock_file = p.dir / ".ai" / ".ledger.lock"
        # Simulate active lock held by another process
        lock_file.write_text("locked", encoding="utf-8")
        code, out = p.osr("start", "T1", "--model", "m")
        # Should detect that lock is held
        self.assertNotEqual(code, 0)
        self.assertIn("lock", out.lower())
        # Removing lock allows operation to succeed
        lock_file.unlink()
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertEqual(code, 0, out)

    def test_verify_command_must_be_confirmed(self):
        p = self.p
        p.setup_ready()
        # Task card with unconfirmed verify command
        bad_card = CARD.replace('verify: "%s" -m unittest tests.test_calc -q' % sys.executable, 'verify: random-runner tests/')
        p.write(".ai/tasks/T1.md", bad_card)
        code, out = p.osr("task-check", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("confirmed", out.lower())

    def test_red_green_baseline_recorded_at_start(self):
        p = self.p
        p.setup_ready()
        # When start runs, verify that baseline is captured
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertEqual(code, 0, out)
        led = [json.loads(line) for line in p.read(".ai/ledger.jsonl").splitlines()]
        start_entry = [e for e in led if e["type"] == "start"][-1]
        self.assertIn("baseline", start_entry["data"])

    def test_cheat_verify_true_rejected(self):
        p = self.p
        p.setup_ready()
        cheat_card = CARD.replace('verify: "%s" -m unittest tests.test_calc -q' % sys.executable, 'verify: true')
        p.write(".ai/tasks/T1.md", cheat_card)
        code, out = p.osr("task-check", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("cannot prove anything", out)

    def test_criteria_test_traceability_blocks_done_when_missing(self):
        p = self.p
        p.setup_ready()
        custom_plan = PLAN.replace("- AC: add(2,3) returns 5 and add(-1,1) returns 0", "- AC: [test_special] add(2,3) returns 5 and add(-1,1) returns 0")
        p.write(".ai/PLAN.md", custom_plan)
        p.osr("approve-plan", "--by", "human")
        p.osr("start", "T1", "--model", "m")
        p.implement()
        code, out = p.osr("verify", "T1")
        self.assertEqual(code, 0, out)
        p.write(".ai/reviews/T1.spec.md", SPEC_OK)
        p.osr("review", "T1", "spec", "--reviewer", "model-b")
        p.write(".ai/reviews/T1.quality.md", QUALITY_OK)
        p.osr("review", "T1", "quality", "--reviewer", "model-b")
        code, out = p.osr("done", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("test_special", out)

    def test_config_tampering_voids_plan_approval(self):
        p = self.p
        p.setup_ready()
        cfg = json.loads(p.read(".ai/config.json"))
        cfg["max_attempts"] = 99
        p.write(".ai/config.json", json.dumps(cfg))
        code, out = p.osr("start", "T1", "--model", "m")
        self.assertNotEqual(code, 0)
        self.assertIn("config", out.lower())
        self.assertIn("approval", out.lower())

    def test_approval_secret_enforcement(self):
        p = self.p
        p.setup_ready(approve=False)
        cfg = json.loads(p.read(".ai/config.json"))
        import hashlib
        cfg["approval_secret_sha"] = hashlib.sha256(b"topsecret123").hexdigest()
        p.write(".ai/config.json", json.dumps(cfg))
        code, out = p.osr("approve-plan", "--by", "human")
        self.assertNotEqual(code, 0)
        self.assertIn("secret", out.lower())
        code, out = p.osr("approve-plan", "--by", "human", "--secret", "wrongsecret")
        self.assertNotEqual(code, 0)
        self.assertIn("secret", out.lower())
        code, out = p.osr("approve-plan", "--by", "human", "--secret", "topsecret123")
        self.assertEqual(code, 0, out)

    def test_anchor_verification_detects_ledger_rollback(self):
        p = self.p
        p.setup_ready()
        code, out = p.osr("anchor")
        self.assertEqual(code, 0, out)
        anchor_file = p.dir / ".osr-anchor"
        self.assertTrue(anchor_file.exists())
        code, out = p.osr("ledger-verify")
        self.assertEqual(code, 0, out)
        lines = p.read(".ai/ledger.jsonl").splitlines()
        p.write(".ai/ledger.jsonl", "\n".join(lines[:-1]) + "\n")
        code, out = p.osr("ledger-verify")
        self.assertNotEqual(code, 0)
        self.assertIn("anchor", out.lower())


if __name__ == "__main__":
    unittest.main()
