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
ROOT_DIR = Path(__file__).resolve().parent.parent

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

    def git_init(self):
        subprocess.run(["git", "init"], cwd=str(self.dir), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.dir), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(self.dir), capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(self.dir), capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=str(self.dir), capture_output=True)

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

    def test_antigravity_pre_tool_hook_blocks_out_of_scope_edits(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "test-model")
        hook_script = ROOT_DIR / "integrations" / "antigravity" / "pre_tool.py"
        self.assertTrue(hook_script.exists(), "integrations/antigravity/pre_tool.py must exist")

        payload = {
            "toolCall": {"name": "edit_file", "args": {"Path": str(p.dir / "src" / "other.py")}},
            "workspacePaths": [str(p.dir)],
        }
        res = subprocess.run([sys.executable, str(hook_script)], input=json.dumps(payload), capture_output=True, text=True, cwd=str(p.dir))
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("decision"), "deny")
        self.assertIn("scope", data.get("reason", "").lower())

        payload = {
            "toolCall": {"name": "edit_file", "args": {"Path": str(p.dir / "src" / "calc.py")}},
            "workspacePaths": [str(p.dir)],
        }
        res = subprocess.run([sys.executable, str(hook_script)], input=json.dumps(payload), capture_output=True, text=True, cwd=str(p.dir))
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("decision"), "allow")

    def test_antigravity_pre_tool_hook_blocks_human_commands(self):
        p = self.p
        p.setup_ready()
        hook_script = ROOT_DIR / "integrations" / "antigravity" / "pre_tool.py"
        self.assertTrue(hook_script.exists())

        payload = {
            "toolCall": {"name": "run_command", "args": {"CommandLine": "python scripts/osr.py approve-plan --by bot"}},
            "workspacePaths": [str(p.dir)],
        }
        res = subprocess.run([sys.executable, str(hook_script)], input=json.dumps(payload), capture_output=True, text=True, cwd=str(p.dir))
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("decision"), "deny")
        self.assertIn("human", data.get("reason", "").lower())

    def test_antigravity_stop_hook_forces_continuation_when_tasks_pending(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "test-model")
        stop_script = ROOT_DIR / "integrations" / "antigravity" / "stop_hook.py"
        self.assertTrue(stop_script.exists(), "integrations/antigravity/stop_hook.py must exist")

        payload = {
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [str(p.dir)],
        }
        res = subprocess.run([sys.executable, str(stop_script)], input=json.dumps(payload), capture_output=True, text=True, cwd=str(p.dir))
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data.get("terminationBehavior"), "force_continue")

    def test_git_pre_commit_hook(self):
        p = self.p
        p.setup_ready()
        pre_commit_script = ROOT_DIR / "integrations" / "git" / "pre_commit.py"
        self.assertTrue(pre_commit_script.exists())
        res = subprocess.run([sys.executable, str(pre_commit_script)], capture_output=True, text=True, cwd=str(p.dir))
        self.assertEqual(res.returncode, 0)

        p.write(".ai/ledger.jsonl", "corrupted json line\n")
        res = subprocess.run([sys.executable, str(pre_commit_script)], capture_output=True, text=True, cwd=str(p.dir))
        self.assertNotEqual(res.returncode, 0)

    def test_review_pack_bundles_diff_card_criteria_without_builder_logs(self):
        p = self.p
        p.setup_ready()
        p.osr("start", "T1", "--model", "secret-builder-model-v99")
        p.implement()
        p.osr("verify", "T1")
        code, out = p.osr("review-pack", "T1")
        self.assertEqual(code, 0, out)
        self.assertIn("R1", out)
        self.assertIn("add(2,3)", out)
        self.assertIn("diff", out.lower())
        self.assertNotIn("secret-builder-model-v99", out)

    def test_quick_path_verifies_without_task_cards(self):
        p = self.p
        p.setup_ready()
        p.git_init()
        p.write("src/calc.py", GOOD_CODE)
        p.write("tests/test_calc.py", GOOD_TEST)
        cmd = f'"{sys.executable}" -m unittest tests.test_calc -q'
        code, out = p.osr("quick", "--verify", cmd, "--allowed", "src/calc.py, tests/test_calc.py")
        self.assertEqual(code, 0, out)
        self.assertIn("PASS", out)

    def test_quick_path_rejects_scope_violation(self):
        p = self.p
        p.setup_ready()
        p.git_init()
        p.write("src/calc.py", GOOD_CODE)
        p.write("src/unauthorized.py", "# out of scope\n")
        cmd = f'"{sys.executable}" -m unittest discover -s tests -q'
        code, out = p.osr("quick", "--verify", cmd, "--allowed", "src/calc.py")
        self.assertNotEqual(code, 0)
        self.assertIn("scope", out.lower())

    def test_pluggable_checkers_in_config_block_on_failure(self):
        p = self.p
        p.setup_ready()
        # Add pluggable checker to config before starting
        cfg_path = p.dir / ".ai" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["checkers"] = [
            {
                "name": "custom_linter",
                "cmd": f'"{sys.executable}" -c "import sys, json; sys.stdout.write(json.dumps({{\\"ok\\": False, \\"flags\\": [\\"custom_violation\\"], \\"errors\\": [\\"Rule 42 failed\\"]}})); sys.exit(1)"'
            }
        ]
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        # Re-approve plan to lock in modified config hash
        code, out = p.osr("approve-plan", "--by", "human")
        self.assertEqual(code, 0, out)
        p.osr("start", "T1", "--model", "gemini-flash")
        p.implement()
        code, out = p.osr("check", "T1")
        self.assertNotEqual(code, 0)
        self.assertIn("custom_violation", out)

    def test_adversarial_eval_suite_benchmarks_catch_rate(self):
        # Must import and run evals.eval_suite benchmark
        from evals.eval_suite import run_adversarial_benchmark
        report = run_adversarial_benchmark()
        self.assertIn("catch_rate", report)
        self.assertEqual(report["catch_rate"], 1.0)
        self.assertEqual(report["false_positive_rate"], 0.0)
        self.assertGreaterEqual(report["total_cheats_tested"], 12)
        self.assertEqual(len(report["caught_vectors"]), 9)
        self.assertEqual(len(report["known_misses"]), 3)
        self.assertIn("V10", [v["id"] for v in report["caught_vectors"]])
        miss_ids = [m["id"] for m in report["known_misses"]]
        self.assertEqual(miss_ids, ["V9", "V11", "V12"])

    def test_seams_plan_check_warning_when_seams_table_missing(self):
        p = Project()
        try:
            p.osr("init")
            # PLAN mentions external API/service/socket/queue in requirement R1, but has no Seams table
            plan_with_external = """# Plan: Service Integration
## Goal
Integrate external user service.
## Non-goals
None.
## Requirements
- R1: Consumer connects to external user service API endpoint
  - AC: fetches user details over HTTP REST endpoint successfully
  - Check: auto
## Assumptions
- [x] Python 3 only
## Open questions
"""
            p.write(".ai/PLAN.md", plan_with_external)
            code, out = p.osr("plan-check")
            self.assertEqual(code, 0)
            self.assertIn("PLAN WARNING:", out)
            self.assertIn("Seams table is empty", out)
        finally:
            p.cleanup()

    def test_seams_plan_check_passes_with_seams_table(self):
        p = Project()
        try:
            p.osr("init")
            plan_with_seams = """# Plan: Service Integration
## Goal
Integrate external user service.
## Non-goals
None.
## Requirements
- R1: Consumer connects to external user service API endpoint
  - AC: fetches user details over HTTP REST endpoint successfully
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user-api | client | user-service | services/user_service.py | contract-test |

## Assumptions
- [x] Python 3 only
## Open questions
"""
            p.write(".ai/PLAN.md", plan_with_seams)
            code, out = p.osr("plan-check")
            self.assertEqual(code, 0)
            self.assertNotIn("PLAN WARNING:", out)
            self.assertIn("PLAN OK:", out)
        finally:
            p.cleanup()

    def test_task_check_enforces_seam_authoritative_source_in_context_files(self):
        p = Project()
        try:
            p.osr("init")
            plan_text = """# Plan: Service Integration
## Goal
Integrate external user service.
## Non-goals
None.
## Requirements
- R1: Consumer connects to external user service API endpoint
  - AC: fetches user details over HTTP REST endpoint successfully
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user-api | client | user-service | services/user_service.py | contract-test |

## Assumptions
- [x] Python 3 only
## Open questions
"""
            p.write(".ai/PLAN.md", plan_text)
            p.write("services/user_service.py", "# Upstream source\n")

            # 1. Failing card: declares seam 'user-api', but context_files omits 'services/user_service.py'
            card_missing_source = f"""# T1: Consumer Task
id: T1
requirements: R1
seams: user-api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -q

## Goal
Consumer task.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write(".ai/tasks/T1.md", card_missing_source)
            code, out = p.osr("task-check", "T1")
            self.assertNotEqual(code, 0)
            self.assertIn("services/user_service.py", out)
            self.assertIn("missing from context_files", out)

            # 2. Cheat attempt: using an unauthorized context_contracts field instead of context_files
            card_cheat = f"""# T1: Consumer Task
id: T1
requirements: R1
seams: user-api
context_contracts: services/user_service.py
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -q

## Goal
Cheat attempt.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write(".ai/tasks/T1.md", card_cheat)
            code, out = p.osr("task-check", "T1")
            self.assertNotEqual(code, 0)
            self.assertIn("missing from context_files", out)

            # 3. Undeclared seam in card fails
            card_unknown_seam = f"""# T1: Consumer Task
id: T1
requirements: R1
seams: non-existent-seam
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_service.py
verify: "{sys.executable}" -m unittest discover -s tests -q

## Goal
Unknown seam.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write(".ai/tasks/T1.md", card_unknown_seam)
            code, out = p.osr("task-check", "T1")
            self.assertNotEqual(code, 0)
            self.assertIn("non-existent-seam", out)

            # 4. Valid card with seam source in context_files passes cleanly
            card_valid = f"""# T1: Consumer Task
id: T1
requirements: R1
seams: user-api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_service.py
verify: "{sys.executable}" -m unittest discover -s tests -q

## Goal
Valid seam card.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write(".ai/tasks/T1.md", card_valid)
            code, out = p.osr("task-check", "T1")
            self.assertEqual(code, 0, out)
            self.assertIn("T1: OK", out)

            # 5. Card with no seams: field behaves exactly as before
            card_no_seams = f"""# T1: Normal Task
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -q

## Goal
Normal card without seams.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write(".ai/tasks/T1.md", card_no_seams)
            code, out = p.osr("task-check", "T1")
            self.assertEqual(code, 0, out)
            self.assertIn("T1: OK", out)
        finally:
            p.cleanup()

    def test_quality_review_seam_citations_enforcement(self):
        p = Project()
        try:
            p.osr("init")
            cfg = json.loads(p.read(".ai/config.json"))
            cfg["commands"] = {"test": {"cmd": f'"{sys.executable}" -m unittest discover -s tests -t . -q', "verified": False}}
            cfg["global_verify"] = ["test"]
            p.write(".ai/config.json", json.dumps(cfg))
            p.osr("confirm-commands")

            plan_text = """# Plan: Service Integration
## Goal
Integrate external user service.
## Non-goals
None.
## Requirements
- R1: Consumer connects to external user service API endpoint
  - AC: fetches user details over HTTP REST endpoint successfully
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user-api | client | user-service | services/user_service.py | contract-test |

## Assumptions
- [x] Python 3 only
## Open questions
"""
            p.write(".ai/PLAN.md", plan_text)
            p.write("services/user_service.py", '"""User service authoritative source."""\ndef fetch_user(uid):\n    return {"user_id": uid, "name": "Alice"}\n')

            card_with_seam = f"""# T1: Consumer Task
id: T1
requirements: R1
seams: user-api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_service.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -q

## Goal
Consumer task with seam.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write(".ai/tasks/T1.md", card_with_seam)
            p.osr("approve-plan", "--by", "human")
            p.osr("start", "T1", "--model", "model-a")
            p.implement()
            code, out = p.osr("verify", "T1")
            self.assertEqual(code, 0, out)

            # Pass spec review first
            p.write(".ai/reviews/T1.spec.md", 'R1: PASS @ src/calc.py:2 "def add(a, b):"\n\nVERDICT: PASS\n')
            code, out = p.osr("review", "T1", "spec", "--reviewer", "model-b")
            self.assertEqual(code, 0, out)

            # 1. Quality review missing seam citations when seams: user-api is declared -> must be rejected
            base_quality = """C1: PASS - inspected all imports
C2: PASS - edge cases handled properly
C3: NA - no user credentials involved
C4: PASS - no TODO or placeholder stubs
C5: PASS - callers match signature
C6: PASS - tests assert exact outputs
C7: PASS - style matches existing code
C8: PASS - only allowed files changed

BREAK_ATTEMPTS:
- Pass empty string and verify graceful error handling
- Pass oversized number and verify no memory exhaustion
- Run concurrently and verify no race condition

VERDICT: PASS
"""
            p.write(".ai/reviews/T1.quality.md", base_quality)
            code, out = p.osr("review", "T1", "quality", "--reviewer", "model-b")
            self.assertNotEqual(code, 0)
            self.assertIn("user-api", out)
            self.assertIn("citation", out.lower())

            # 2. Quality review citing only consumer files (src/calc.py) for the seam -> must be rejected
            consumer_citation_quality = base_quality + '\n## Seams\nSEAM user-api: @ src/calc.py:2 "def add(a, b):"\n'
            p.write(".ai/reviews/T1.quality.md", consumer_citation_quality)
            code, out = p.osr("review", "T1", "quality", "--reviewer", "model-b")
            self.assertNotEqual(code, 0)
            self.assertIn("services/user_service.py", out)

            # 3. Quality review citing upstream authoritative source correctly -> must pass
            valid_seam_quality = base_quality + '\n## Seams\nSEAM user-api: @ services/user_service.py:2 "def fetch_user(uid):"\n'
            p.write(".ai/reviews/T1.quality.md", valid_seam_quality)
            code, out = p.osr("review", "T1", "quality", "--reviewer", "model-b")
            self.assertEqual(code, 0, out)
            self.assertIn("REVIEW RECORDED: quality PASS", out)
        finally:
            p.cleanup()





if __name__ == "__main__":
    unittest.main()
