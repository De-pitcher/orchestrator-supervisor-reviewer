#!/usr/bin/env python3
"""Git pre-commit hook verifying OSR ledger and plan integrity."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main():
    root = Path.cwd()
    osr = root / "scripts" / "osr.py"
    if not osr.exists():
        osr = Path(__file__).resolve().parent.parent.parent / "scripts" / "osr.py"

    if osr.exists():
        cmd_base = [sys.executable, str(osr)]
    else:
        osr_bin = shutil.which("osr")
        cmd_base = [osr_bin] if osr_bin else None

    if not cmd_base:
        sys.exit(0)

    # 1. Verify ledger
    res_ledger = subprocess.run(cmd_base + ["--root", str(root), "ledger-verify"], capture_output=True, text=True)
    if res_ledger.returncode != 0:
        print("PRE-COMMIT ERROR: Ledger integrity violation:")
        print(res_ledger.stdout or res_ledger.stderr)
        sys.exit(1)

    # 2. Verify plan
    res_plan = subprocess.run(cmd_base + ["--root", str(root), "plan-check"], capture_output=True, text=True)
    if res_plan.returncode != 0:
        print("PRE-COMMIT ERROR: PLAN.md is invalid:")
        print(res_plan.stdout or res_plan.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
