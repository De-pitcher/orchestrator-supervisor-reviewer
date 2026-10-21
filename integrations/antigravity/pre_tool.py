#!/usr/bin/env python3
"""Pre-tool enforcement hook for Antigravity.

Enforces:
1. Iron Rule 10: hard-blocks agent execution of human-only commands (approve-plan, unblock, signoff, reset).
2. Protects against secret inspection.
3. Scope enforcement: hard-blocks file modifications outside allowed_files for the currently active task.
"""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path


def matches_pattern(path_str: str, pat: str) -> bool:
    path_str = path_str.replace("\\", "/").lstrip("./")
    pat = pat.replace("\\", "/").lstrip("./")
    if pat.endswith("/**"):
        prefix = pat[:-3].rstrip("/")
        return path_str == prefix or path_str.startswith(prefix + "/")
    if pat.endswith("/*"):
        prefix = pat[:-2].rstrip("/")
        parts = path_str.split("/")
        prefix_parts = prefix.split("/")
        return len(parts) == len(prefix_parts) + 1 and path_str.startswith(prefix + "/")
    return fnmatch.fnmatch(path_str, pat)


def main():
    try:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    ws = payload.get("workspacePaths", [])
    root = Path(ws[0]).resolve() if ws else Path.cwd()

    tool_call = payload.get("toolCall", {})
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})

    # 1. Block human-only commands in run_command
    if name == "run_command":
        cmd = args.get("CommandLine", "")
        if re.search(r"\bosr\b", cmd, re.IGNORECASE) and re.search(r"\b(approve-plan|unblock|signoff|reset)\b", cmd, re.IGNORECASE):
            print(json.dumps({
                "decision": "deny",
                "reason": "Iron Rule 10: osr approve-plan/unblock/reset/signoff is human-only and blocked from agent execution."
            }))
            sys.exit(0)
        if re.search(r"OSR_APPROVAL_SECRET|\.osr-secret", cmd):
            print(json.dumps({
                "decision": "deny",
                "reason": "Access to approval secrets is blocked."
            }))
            sys.exit(0)

    # 2. Scope enforcement for file edits
    if name in ("edit_file", "write_file"):
        target_path_str = args.get("Path", "")
        if target_path_str:
            p = Path(target_path_str)
            try:
                rel = p.resolve().relative_to(root).as_posix() if p.is_absolute() else p.as_posix()
            except ValueError:
                rel = p.as_posix()

            state_file = root / ".ai" / "state.json"
            if state_file.exists():
                try:
                    st = json.loads(state_file.read_text(encoding="utf-8"))
                    active_task = None
                    for tid, tinfo in st.get("tasks", {}).items():
                        if tinfo.get("status") == "in_progress":
                            active_task = tid
                            break
                    if active_task:
                        card_file = root / ".ai" / "tasks" / f"{active_task}.md"
                        if card_file.exists():
                            card_text = card_file.read_text(encoding="utf-8")
                            allowed_patterns = []
                            for line in card_text.splitlines():
                                if line.startswith("allowed_files:"):
                                    parts = line.split(":", 1)[1].split(",")
                                    allowed_patterns = [pt.strip() for pt in parts if pt.strip()]
                                    break
                            if allowed_patterns:
                                allowed = any(matches_pattern(rel, pat) for pat in allowed_patterns)
                                if not allowed:
                                    print(json.dumps({
                                        "decision": "deny",
                                        "reason": f"Scope violation: file '{rel}' is not in allowed_files for active task {active_task}."
                                    }))
                                    sys.exit(0)
                except Exception:
                    pass

    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
