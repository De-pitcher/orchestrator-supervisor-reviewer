"""Adversarial test suite verifying the 14 hardening hypotheses for osr v0.3.0.

Run: python -m unittest tests.test_hardening_hypotheses -v
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

OSR = str(Path(__file__).resolve().parent.parent / "scripts" / "osr.py")
ROOT_DIR = Path(__file__).resolve().parent.parent


class TestProject:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="osr-hardening-"))
        self.write("src/__init__.py", "")
        self.write("tests/__init__.py", "")
        self.write("tests/test_base.py", "import unittest\nclass B(unittest.TestCase):\n    def test_b(self):\n        self.assertEqual(1, 1)\n")

    def cleanup(self):
        try:
            shutil.rmtree(self.dir, ignore_errors=True)
        except Exception:
            pass

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, rel):
        return (self.dir / rel).read_text(encoding="utf-8")

    def osr(self, *args):
        cmd = [sys.executable, OSR, "--root", str(self.dir)] + list(args)
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def setup_project(self, plan_text, card_text):
        self.osr("init")
        cfg = json.loads(self.read(".ai/config.json"))
        test_cmd = f'"{sys.executable}" -m unittest discover -s tests -t . -q'
        cfg["commands"] = {"test": {"cmd": test_cmd, "verified": False}}
        cfg["global_verify"] = ["test"]
        self.write(".ai/config.json", json.dumps(cfg))
        self.osr("confirm-commands")
        self.write(".ai/PLAN.md", plan_text)
        self.write(".ai/tasks/T1.md", card_text)
        self.osr("approve-plan", "--by", "human")


class HardeningHypothesesTests(unittest.TestCase):

    def test_h1_fabricated_fixture_provenance_and_mandatory_conformance(self):
        """H1: A builder invents a wrong-shaped fixture, registers it, loads it in mock without conformance.
        Does verify pass? CONFIRMED if verify passes without conformance checking.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test user API integration.
## Non-goals
None.
## Requirements
- R1: User format
  - AC: formats user from fixture payload [test_user]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | services/user_api.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
            p.write("services/user_api.py", "# Real schema: fields 'account_id', 'full_name'\n")
            # Fabricated fixture with wrong fields invented by builder
            p.write("fixtures/fabricated_user.json", '{"wrong_id": 999, "fake_field": "ghost"}')
            
            card = f"""# T1: Task
id: T1
requirements: R1
seams: user_api
fixtures: fixtures/fabricated_user.json
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_api.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Fabricate fixture test.
## Constraints
None.
## Do not
None.
## Definition of done
Completed test.
"""
            p.setup_project(plan, card)
            # Register fabricated fixture with fake provenance
            code, out = p.osr("fixture-add", "fixtures/fabricated_user.json", "--seam", "user_api", "--source", "captured from prod")
            self.assertEqual(code, 0)
            
            code, out = p.osr("start", "T1")
            self.assertEqual(code, 0, out)
            
            p.write("src/calc.py", 'import json\ndef get_user_name():\n    with open("fixtures/fabricated_user.json", encoding="utf-8") as f:\n        data = json.load(f)\n    return data["fake_field"]\n')
            p.write("tests/test_calc.py", 'import unittest\nimport src.calc as calc\nclass T(unittest.TestCase):\n    def test_user(self):\n        self.assertEqual(calc.get_user_name(), "ghost")\n')
            code, out = p.osr("verify", "T1")
            self.assertEqual(code, 0, out)

            p.write(".ai/reviews/T1.spec.md", 'R1: PASS @ src/calc.py:2 "def get_user_name():"\n\nVERDICT: PASS\n')
            p.osr("review", "T1", "spec", "--reviewer", "peer")
            quality_body = """C1: PASS - standard library imports and functions resolve cleanly
C2: PASS - handles empty input and missing fields safely
C3: NA - local file read only, no credentials or network operations
C4: PASS - no placeholders, stubs, or truncation markers present
C5: PASS - caller interface signatures verified unchanged
C6: PASS - assertions verify expected fake field value
C7: PASS - conforms to python formatting and idioms
C8: PASS - within allowed_files boundaries strictly

## Seams
SEAM user_api: @ services/user_api.py:1 "# Real schema"

BREAK_ATTEMPTS:
- Attempt 1: feed corrupted json file to get_user_name
- Attempt 2: feed empty json dictionary without fake_field
- Attempt 3: delete fixture file to observe file missing error

VERDICT: PASS
"""
            p.write(".ai/reviews/T1.quality.md", quality_body)
            p.osr("review", "T1", "quality", "--reviewer", "peer")
            code_d, out_d = p.osr("done", "T1")
            self.assertEqual(code_d, 0, out_d)

            # In v0.3.1, audit blocks with exit 2 (UNVERIFIED) for seam without conformance
            code_audit, out_audit = p.osr("audit")
            self.assertEqual(code_audit, 2, "H1 MITIGATED: Audit must exit 2 with UNVERIFIED for missing conformance")
            self.assertIn("UNVERIFIED", out_audit)
            self.assertIn("missing conformance", out_audit.lower())
        finally:
            p.cleanup()

    def test_h2_bogus_seam_source_declared_in_plan(self):
        """H2: A card declares an invented mock/fixture file as authoritative source.
        Does task-check catch it? CONFIRMED if task-check passes.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test bogus seam source.
## Non-goals
None.
## Requirements
- R1: User format
  - AC: formats user from bogus source [test_user]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | tests/mocks/fake_source.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
            # An invented fake source file inside tests/mocks/
            p.write("tests/mocks/fake_source.py", "# Bogus provider mock source\n")
            card = f"""# T1: Task
id: T1
requirements: R1
seams: user_api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, tests/mocks/fake_source.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Bogus seam source task.
## Constraints
None.
## Do not
None.
## Definition of done
Completed.
"""
            p.osr("init")
            p.write(".ai/PLAN.md", plan)
            p.write(".ai/tasks/T1.md", card)
            code, out = p.osr("task-check", "T1")
            self.assertNotEqual(code, 0, "H2 MITIGATED: Bogus mock/test file rejected as authoritative seam source")
            self.assertIn("authoritative source", out.lower())
        finally:
            p.cleanup()

    def test_h3_citation_path_mismatch_is_rejected(self):
        """H3: Quality review cites a seam from a non-authoritative file.
        REFUTED if quality review rejects citation path mismatch.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test citation path mismatch.
## Non-goals
None.
## Requirements
- R1: User format
  - AC: formats user correctly [test_user]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | services/user_api.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
            p.write("services/user_api.py", "user_id = 42\n")
            p.write("src/consumer.py", "user_id = 42\n")
            card = f"""# T1: Task
id: T1
requirements: R1
seams: user_api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_api.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Citation test.
## Constraints
None.
## Do not
None.
## Definition of done
Completed.
"""
            p.write("scripts/test_manual.py", "# manual wire test script\n")
            p.setup_project(plan, card)
            p.osr("start", "T1", "--model", "peer")
            p.write("src/calc.py", "def get_id(): return 42\n")
            p.write("tests/test_calc.py", "import unittest\nfrom src.calc import get_id\nclass T(unittest.TestCase):\n    def test_user(self): self.assertEqual(get_id(), 42)\n")
            p.osr("verify", "T1")
            # Submit spec review first
            p.write(".ai/reviews/T1.spec.md", 'R1: PASS @ src/calc.py:1 "def get_id(): return 42"\n\nVERDICT: PASS\n')
            code_spec, out_spec = p.osr("review", "T1", "spec", "--reviewer", "peer")
            self.assertEqual(code_spec, 0, out_spec)
            
            # Review cites consumer.py instead of declared services/user_api.py
            p.write(".ai/reviews/T1.quality.md", """C1: PASS - checked imports
C2: PASS - checked none
C3: NA - no network
C4: PASS - no stubs
C5: PASS - caller match
C6: PASS - tests pass
C7: PASS - matches style
C8: PASS - within scope

## Seams
SEAM user_api: @ src/consumer.py:1 "user_id = 42"

BREAK_ATTEMPTS:
- Attempt 1: check invalid return types
- Attempt 2: check None payload
- Attempt 3: check empty string

VERDICT: PASS
""")
            code, out = p.osr("review", "T1", "quality", "--reviewer", "peer")
            # Gate should reject citation path mismatch
            gate_stopped_it = (code != 0) and ("authoritative source is 'services/user_api.py'" in out)
            self.assertTrue(gate_stopped_it, "H3 REFUTED: Citation path mismatch was properly stopped by the gate")
        finally:
            p.cleanup()

    def test_h4_evaded_mock_detection_custom_stub(self):
        """H4: Mock created via manual stub class or monkeypatch without registered fixture.
        Does unanchored-mock flag it? CONFIRMED if evasion succeeds without warning.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test mock evasion.
## Non-goals
None.
## Requirements
- R1: Calc
  - AC: calculation done [test_calc]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | services/user_api.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
            p.write("services/user_api.py", "class Client:\n    def fetch(self): return {'real': 1}\n")
            card = f"""# T1: Task
id: T1
requirements: R1
seams: user_api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_api.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Mock evasion test.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write("scripts/test_manual.py", "# manual wire test script\n")
            p.setup_project(plan, card)
            p.osr("start", "T1", "--model", "peer")
            p.write("src/calc.py", "def do_fetch(client): return client.fetch()['fake_unanchored_field']\n")
            # Hand-rolled stub class without unittest.mock or patch keywords
            p.write("tests/test_calc.py", """import unittest
from src.calc import do_fetch
class FakeStubClient:
    def fetch(self):
        return {'fake_unanchored_field': 'evaded'}

class T(unittest.TestCase):
    def test_calc(self):
        client = FakeStubClient()
        self.assertEqual(do_fetch(client), 'evaded')
""")
            code, out = p.osr("check", "T1")
            cheat_succeeded = (code == 0) and ("unanchored-mock" not in out)
            self.assertTrue(cheat_succeeded, "H4 CONFIRMED: Hand-rolled mock/stub evaded unanchored-mock regex")
        finally:
            p.cleanup()

    def test_h5_tautological_assertion_v11(self):
        """H5: Replacing real assertion with assert 1 == 1 leaves count unchanged.
        CONFIRMED if check passes without flagging.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test tautological assertion.
## Non-goals
None.
## Requirements
- R1: Add
  - AC: add returns sum [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
            card = f"""# T1: Task
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Tautological test.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.setup_project(plan, card)
            # Baseline with 1 real assertion
            p.write("src/calc.py", "def add(a, b): return a + b\n")
            p.write("tests/test_calc.py", "import unittest\nfrom src.calc import add\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(add(2, 3), 5)\n")
            p.osr("start", "T1")
            
            # Cheat: break code, replace assertion with assert 1 == 1 (assertion count remains 1)
            p.write("src/calc.py", "def add(a, b): return 'broken'\n")
            p.write("tests/test_calc.py", "import unittest\nfrom src.calc import add\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(1, 1)\n")
            code, out = p.osr("check", "T1")
            self.assertNotEqual(code, 0, "H5 MITIGATED: Tautological assertion assert 1 == 1 caught by AST check")
            self.assertIn("tautological-assertion", out.lower())
        finally:
            p.cleanup()

    def test_h6_weak_verify_command_zero_tests_v12(self):
        """H6: Verify command matches zero tests or is a grep that checks token presence instead of behavior (V12).
        CONFIRMED if verify passes on broken code.
        """
        p = TestProject()
        try:
            # Grep-style command that checks token existence without testing behavior
            weak_cmd = f'"{sys.executable}" -c "import sys, pathlib; sys.exit(0 if \'def add\' in pathlib.Path(\'src/calc.py\').read_text() else 1)"'
            plan = """# Plan
## Goal
Test weak verify command.
## Non-goals
None.
## Requirements
- R1: Add calculation
  - AC: add returns sum [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
            card = f"""# T1: Task
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: {weak_cmd}

## Goal
Weak verify test.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.setup_project(plan, card)
            code, out = p.osr("start", "T1")
            self.assertNotEqual(code, 0, "H6 MITIGATED: start rejects weak verify command")
            self.assertIn("weak verify command", out.lower())
            self.assertTrue("SUSPECT" in out or "weak" in out.lower())
        finally:
            p.cleanup()

    def test_h7_negative_tests_semantic_vacuity(self):
        """H7: negative_tests names a test that runs but asserts nothing (e.g. pass).
        CONFIRMED if verify passes.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test negative tests vacuity.
## Non-goals
None.
## Requirements
- R1: Calc
  - AC: calculation done [test_valid]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | services/user_api.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
            p.write("services/user_api.py", "# Upstream source\n")
            card = f"""# T1: Task
id: T1
requirements: R1
seams: user_api
negative_tests: test_empty_user_vacuous
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_api.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Vacuous negative test.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write("scripts/test_manual.py", "# manual wire test script\n")
            p.setup_project(plan, card)
            p.osr("start", "T1", "--model", "peer")
            p.write("src/calc.py", "def get_user(): return {}\n")
            # Empty negative test with pass, asserting nothing
            p.write("tests/test_calc.py", """import unittest
class T(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(len("user"), 4)
    def test_empty_user_vacuous(self):
        pass
""")
            code, out = p.osr("verify", "T1")
            cheat_succeeded = (code == 0)
            self.assertTrue(cheat_succeeded, "H7 CONFIRMED: Vacuous negative test with no assertions passed verify")
        finally:
            p.cleanup()

    def test_h8_quick_path_cannot_mark_tasks_done(self):
        """H8: Can osr quick be used to bypass review gates on formal tasks?
        REFUTED if quick does not mark tasks done.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test quick path task bypass.
## Non-goals
None.
## Requirements
- R1: Add
  - AC: add returns sum [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
            card = f"""# T1: Task
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Task.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.setup_project(plan, card)
            p.osr("start", "T1", "--model", "peer")
            p.write("src/calc.py", "def add(a, b): return a + b\n")
            p.write("tests/test_calc.py", "import unittest\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(1, 1)\n")
            
            # Run osr quick
            code, out = p.osr("quick", "--verify", f'"{sys.executable}" -m unittest discover -s tests -t . -q', "--allowed", "src/calc.py,tests/test_calc.py,src/__init__.py,tests/__init__.py,tests/test_base.py")
            self.assertEqual(code, 0, out)
            
            # Check state of T1
            state = json.loads(p.read(".ai/state.json"))
            t1_status = state["tasks"]["T1"]["status"]
            task_marked_done = (t1_status == "done")
            self.assertFalse(task_marked_done, "H8 REFUTED: osr quick does not mark task cards done")
        finally:
            p.cleanup()

    def test_h9_review_pack_contains_no_builder_reasoning(self):
        """H9: Does review-pack contain builder reasoning or prior review text?
        REFUTED if review pack contains only diff, card, criteria, seams, sources, and adversarial prompt.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test review pack contents.
## Non-goals
None.
## Requirements
- R1: Add
  - AC: add returns sum [test_add]
  - Check: auto
## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| user_api | consumer | provider | services/user_api.py | contract-test |
## Assumptions
- [x] Python 3
## Open questions
"""
            p.write("services/user_api.py", "USER_FIELD = 'id'\n")
            card = f"""# T1: Task
id: T1
requirements: R1
seams: user_api
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md, services/user_api.py
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Review pack test.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write("scripts/test_manual.py", "# manual wire test script\n")
            p.setup_project(plan, card)
            p.osr("start", "T1", "--model", "peer")
            p.write("src/calc.py", "def add(a, b): return a + b\n")
            p.write("tests/test_calc.py", "import unittest\nclass T(unittest.TestCase):\n    def test_add(self): self.assertEqual(1, 1)\n")
            code, pack = p.osr("review-pack", "T1")
            self.assertEqual(code, 0)
            
            has_adversarial = "Adversarial Review Directive" in pack
            has_seams = "Declared Seams" in pack
            has_builder_logs = "builder reasoning" in pack.lower() or "attempt 1 failed" in pack.lower()
            self.assertTrue(has_adversarial)
            self.assertTrue(has_seams)
            self.assertFalse(has_builder_logs, "H9 REFUTED: review pack leaked builder logs")
        finally:
            p.cleanup()

    def test_h10_manual_path_audit_exit_code_2(self):
        """H10: Can Check: manual pass audit without human signoff?
        REFUTED if audit exits 2 and marks UNVERIFIED.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test manual path.
## Non-goals
None.
## Requirements
- R1: Automated calculation logic
  - AC: calculation returns correct sum [test_calc]
  - Check: auto
- R2: WebSocket wire protocol timing
  - AC: wire timing validated against real server with script
  - Check: manual
  - Script: scripts/test_wire.py
## Assumptions
- [x] Python 3 only
## Open questions
"""
            card = f"""# T1: Calc task
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Implement calc.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.write("scripts/test_wire.py", "# Manual wire timing verification script\nprint('Wire ok')\n")
            p.setup_project(plan, card)
            p.osr("start", "T1", "--model", "peer")
            p.write("src/calc.py", "def add(a, b): return a + b\n")
            p.write("tests/test_calc.py", "import unittest\nfrom src.calc import add\nclass C(unittest.TestCase):\n    def test_calc(self): self.assertEqual(add(1, 2), 3)\n")
            code_v, out_v = p.osr("verify", "T1")
            self.assertEqual(code_v, 0, out_v)
            
            p.write(".ai/reviews/T1.spec.md", 'R1: PASS @ src/calc.py:1 "def add(a, b): return a + b"\n\nVERDICT: PASS\n')
            code_s, out_s = p.osr("review", "T1", "spec", "--reviewer", "peer")
            self.assertEqual(code_s, 0, out_s)
            
            p.write(".ai/reviews/T1.quality.md", """C1: PASS - checked all imports and declared dependencies in package
C2: PASS - handled empty input and None cases thoroughly
C3: NA - no network or filesystem operations performed
C4: PASS - no TODOs, stubs, or placeholder comments
C5: PASS - unchanged caller signatures verified across modules
C6: PASS - tests pass with all assertions intact and verified
C7: PASS - matches existing codebase style and conventions
C8: PASS - within allowed_files scope without extra changes

BREAK_ATTEMPTS:
- Attempt 1: send unexpected payload with extra fields to consumer
- Attempt 2: send empty JSON object to simulate missing fields
- Attempt 3: return null payload to test parser error handling

VERDICT: PASS
""")
            code_q, out_q = p.osr("review", "T1", "quality", "--reviewer", "peer")
            self.assertEqual(code_q, 0, out_q)
            
            code_d, out_d = p.osr("done", "T1")
            self.assertEqual(code_d, 0, out_d)
            
            # Audit must exit 2 with UNVERIFIED because manual requirement R2 was not signed off
            code, out = p.osr("audit")
            gate_held = (code == 2) and ("UNVERIFIED" in out) and ("PENDING-HUMAN" in out)
            self.assertTrue(gate_held, f"H10 REFUTED: Audit exit code 2 strictly held for unsigned manual requirement: {out}")
        finally:
            p.cleanup()

    def test_h11_anchor_in_repo_tamperability(self):
        """H11: An agent rewriting the whole ledger chain can also rewrite in-repo .osr-anchor.
        CONFIRMED if an in-repo anchor does not protect against a model with write permissions to the repo.
        """
        p = TestProject()
        try:
            plan = """# Plan
## Goal
Test anchor rewrite.
## Non-goals
None.
## Requirements
- R1: Add
  - AC: sum returned [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
            card = f"""# T1: Task
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest discover -s tests -t . -v

## Goal
Anchor test.
## Constraints
None.
## Do not
None.
## Definition of done
Done.
"""
            p.setup_project(plan, card)
            # Create in-repo anchor
            p.osr("anchor")
            self.assertTrue((p.dir / ".osr-anchor").exists())
            
            # Agent with repo-write permission can alter ledger and overwrite .osr-anchor
            tampered_ledger = '{"seq": 1, "ts": "fake", "type": "init", "task": null, "attempt": null, "data": {}, "prev": "0000000000000000000000000000000000000000000000000000000000000000", "hash": "abc"}\n'
            p.write(".ai/ledger.jsonl", tampered_ledger)
            p.write(".osr-anchor", json.dumps({"seq": 1, "hash": "abc", "ts": "fake"}))
            
            # The tool can verify against the tampered anchor without detecting tampering if both were overwritten
            anchor_data = json.loads(p.read(".osr-anchor"))
            anchor_overwritten = (anchor_data["hash"] == "abc")
            self.assertTrue(anchor_overwritten, "H11 CONFIRMED: In-repo anchor can be trivially rewritten alongside ledger")
        finally:
            p.cleanup()

    def test_h12_antigravity_hooks_event_schema_contract(self):
        """H12: Test stop_hook.py and pre_tool.py against actual Antigravity hook contracts.
        CONFIRMED if stop_hook returns invalid schema for Stop event.
        """
        # Test stop_hook.py with empty stdin
        proc = subprocess.run([sys.executable, str(ROOT_DIR / "integrations" / "antigravity" / "stop_hook.py")],
                              input="{}", text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0)
        output_json = json.loads(proc.stdout)
        # Antigravity Stop event contract requires 'decision' and 'reason'
        has_decision = "decision" in output_json
        has_reason = "reason" in output_json
        self.assertTrue(has_decision, "H12 mitigated: stop_hook.py returns decision (Stop schema)")
        self.assertTrue(has_reason, "H12 mitigated: stop_hook.py returns reason (Stop schema)")

    def test_h13_plan_check_false_positive_warning_noise(self):
        """H13: Ordinary non-seam plan mentioning common words triggers heuristic warning.
        CONFIRMED if plan-check prints a seam warning for purely local code.
        """
        p = TestProject()
        try:
            # Plan mentioning 'API' and 'Service' as local classes, with no external seam
            plan = """# Plan
## Goal
Implement UserService and calculate its internal public API.
## Non-goals
None.
## Requirements
- R1: Internal UserService API
  - AC: service method returns user object [test_user]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
            p.osr("init")
            p.write(".ai/PLAN.md", plan)
            code, out = p.osr("plan-check")
            has_warning = "mentions external interface" in out and "but Seams table is empty" in out
            self.assertTrue(has_warning, f"H13 CONFIRMED: plan-check emits heuristic seam warning on local non-seam vocabulary: {out}")
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()
