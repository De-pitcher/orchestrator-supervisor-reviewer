"""Unit tests for Antigravity stop_hook contract compliance."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STOP_HOOK = ROOT / "integrations" / "antigravity" / "stop_hook.py"


class TestStopHookContract(unittest.TestCase):
    def test_stop_hook_contract(self):
        # stop_hook.py must comply with the official Antigravity Stop event contract
        payload = {
            "executionNum": 1,
            "terminationReason": "NO_TOOL_CALL",
            "workspacePaths": [str(ROOT)]
        }
        proc = subprocess.run(
            [sys.executable, str(STOP_HOOK)],
            input=json.dumps(payload),
            text=True,
            capture_output=True
        )
        self.assertEqual(proc.returncode, 0, f"Hook failed: {proc.stderr}")
        data = json.loads(proc.stdout)
        
        # Must contain Stop contract fields
        self.assertIn("decision", data, "Stop hook must return 'decision'")
        self.assertIn("reason", data, "Stop hook must return 'reason'")
        self.assertEqual(data["decision"], "continue", "Unfinished tasks must force decision 'continue'")

    def test_stop_hook_when_no_active_workflow(self):
        # When running in an empty workspace without .ai/, decision must be 'approve'
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = {
                "executionNum": 1,
                "terminationReason": "NO_TOOL_CALL",
                "workspacePaths": [tmpdir]
            }
            proc = subprocess.run(
                [sys.executable, str(STOP_HOOK)],
                input=json.dumps(payload),
                text=True,
                capture_output=True
            )
            self.assertEqual(proc.returncode, 0)
            data = json.loads(proc.stdout)
            self.assertIn("decision", data)
            self.assertEqual(data["decision"], "approve")


if __name__ == "__main__":
    unittest.main()
