#!/usr/bin/env python3
"""
Manual assessment script for R4b:
Attempt to run approve-plan from the real Antigravity agent terminal.
Evaluates whether sys.stdin.isatty() is True and whether getpass works,
or whether execution fails closed. Findings are written to .ai/TTY_ANALYSIS.md.
"""
import sys
import os

def main():
    print(f"=== Antigravity Agent Terminal TTY Assessment ===")
    print(f"sys.stdin.isatty(): {sys.stdin.isatty()}")
    print(f"sys.stdout.isatty(): {sys.stdout.isatty()}")
    print(f"sys.stderr.isatty(): {sys.stderr.isatty()}")
    print(f"TERM: {os.environ.get('TERM', 'not set')}")
    print(f"===============================================")

if __name__ == "__main__":
    main()
