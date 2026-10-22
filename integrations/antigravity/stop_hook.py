#!/usr/bin/env python3
"""Stop lifecycle hook for Antigravity.

Inspects OSR task progress and prevents the agent from terminating when tasks
are in progress or unverified, returning decision: continue with the next action from osr next.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main():
    try:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    ws = payload.get("workspacePaths", [])
    root = Path(ws[0]).resolve() if ws else Path.cwd()

    state_file = root / ".ai" / "state.json"
    if state_file.exists():
        try:
            st = json.loads(state_file.read_text(encoding="utf-8"))
            tasks = st.get("tasks", {})
            incomplete = [tid for tid, tinfo in tasks.items() if tinfo.get("status") != "done"]
            task_files = list((root / ".ai" / "tasks").glob("*.md")) if (root / ".ai" / "tasks").exists() else []
            all_done = bool(task_files) and len(incomplete) == 0 and len(tasks) == len(task_files)

            if not all_done or any(tinfo.get("status") == "in_progress" for tinfo in tasks.values()):
                osr_script = root / "scripts" / "osr.py"
                next_act = "run osr next"
                if osr_script.exists():
                    res = subprocess.run([sys.executable, str(osr_script), "--root", str(root), "next"], capture_output=True, text=True)
                    if res.returncode == 0 and res.stdout.strip():
                        next_act = res.stdout.strip()
                print(json.dumps({
                    "decision": "continue",
                    "reason": f"OSR Gate: workflow is not complete. Next required action: {next_act}",
                    "terminationBehavior": "force_continue",
                    "injectSteps": [
                        {
                            "ephemeralMessage": f"OSR Gate: workflow is not complete. Next required action: {next_act}"
                        }
                    ]
                }))
                sys.exit(0)
        except Exception:
            pass

    print(json.dumps({
        "decision": "approve",
        "reason": "OSR Gate: all tasks complete or no active workflow.",
        "terminationBehavior": "",
        "injectSteps": []
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
