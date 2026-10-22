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
        self.dir = Path(tempfile.mkdtemp(prefix="osr-test-anchor-"))
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
        }
        cfg["global_verify"] = ["test"]
        self.write(".ai/config.json", json.dumps(cfg))
        self.osr("confirm-commands")
        self.write(".ai/PLAN.md", plan_text)
        self.write(".ai/tasks/T1.md", card_text)
        self.osr("approve-plan", "--by", "human")


class TestAnchorExt(unittest.TestCase):
    def setUp(self):
        self.p = TestProject()
        self.external_dir = Path(tempfile.mkdtemp(prefix="osr-ext-vault-"))
        self.addCleanup(self.p.cleanup)
        self.addCleanup(lambda: shutil.rmtree(self.external_dir, ignore_errors=True))

    # R5 Acceptance Test: osr anchor and ledger-verify support optional external anchor
    # file paths with documented threat model [test_external_anchor_verification]
    def test_external_anchor_verification(self):
        p = self.p
        ext_anchor = self.external_dir / "secure.anchor"

        plan = """# Plan
## Goal
Test out of band anchor.
## Non-goals
None.
## Requirements
- R1: Add math
  - AC: calculation done [test_add]
  - Check: auto
## Assumptions
- [x] Python 3
## Open questions
"""
        card = f"""# T1: Add
id: T1
requirements: R1
allowed_files: src/calc.py, tests/test_calc.py
context_files: .ai/PLAN.md
verify: "{sys.executable}" -m unittest tests.test_calc -v

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

        # 1. Capture external anchor using --out <path>
        code, out = p.osr("anchor", "--out", str(ext_anchor))
        self.assertEqual(code, 0, f"anchor --out failed: {out}")
        self.assertTrue(ext_anchor.exists(), "External anchor file must be written")
        anchor_data = json.loads(ext_anchor.read_text(encoding="utf-8"))
        self.assertIn("hash", anchor_data)
        self.assertIn("seq", anchor_data)

        # 2. Verify against untouched external anchor passes
        code, out = p.osr("ledger-verify", "--anchor", str(ext_anchor))
        self.assertEqual(code, 0, f"ledger-verify with valid external anchor failed: {out}")

        # 3. Simulate attacker rolling back repo ledger and in-repo .osr-anchor
        # Truncate ledger to only entry 1 (valid internally, but rolled back compared to anchored seq)
        lines = p.read(".ai/ledger.jsonl").strip().splitlines()
        first_entry = json.loads(lines[0])
        p.write(".ai/ledger.jsonl", lines[0] + "\n")
        p.write(".osr-anchor", json.dumps({"seq": 1, "head_hash": first_entry["hash"], "ts": first_entry.get("ts", "")}))

        # In-repo verify is fooled because the rolled back ledger matches the rewritten in-repo anchor:
        code, out = p.osr("ledger-verify")
        self.assertEqual(code, 0, "In-repo verification is fooled when attacker rewrites in-repo anchor")

        # But verifying against external out-of-band anchor MUST detect tampering/rollback:
        code, out = p.osr("ledger-verify", "--anchor", str(ext_anchor))
        self.assertNotEqual(code, 0, "ledger-verify must reject rolled back ledger when checked against external anchor")
        self.assertIn("anchor mismatch", out.lower())

        # 4. osr audit with --anchor must also reject tampered ledger
        code, out = p.osr("audit", "--anchor", str(ext_anchor))
        self.assertNotEqual(code, 0, "audit --anchor must reject tampered ledger")


if __name__ == "__main__":
    unittest.main()
