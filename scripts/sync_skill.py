#!/usr/bin/env python3
"""
Sync repository skill files with the global Antigravity skill directory.

- Syncs an explicit file set only (SYNC_FILES + SYNC_DIRS below).
- Post-copy SHA-256 hash verification.
- --check compares hashes without writing; exits non-zero and names every offending file.
- Extras in the target are flagged only inside synced items; use --prune (opt-in, sync mode only) to delete them.
- Exclusions are evaluated on root-relative paths, so parent folders named venv/.ai etc. do not matter.
"""

import sys
import shutil
import hashlib
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SYNC_FILES = ["SKILL.md", "PROMPT-ONLY.md", "README.md", "CHANGELOG.md", "LICENSE"]
SYNC_DIRS = ["scripts", "assets", "references", "integrations", "tests", "evals", "examples"]

EXCLUDE_DIRS = {".git", ".ai", "__pycache__", ".pytest_cache", ".ruff_cache", "venv", ".venv"}
EXCLUDE_EXTS = {".pyc", ".pyo", ".log"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def is_excluded(rel):
    """rel is a root-relative Path; only its own components are examined (never the absolute prefix)."""
    if set(rel.parts[:-1]) & EXCLUDE_DIRS:
        return True
    return rel.suffix in EXCLUDE_EXTS


def collect(base):
    """Return {posix-relative-path: sha256} for synced items under base (works for source root and target)."""
    files = {}
    for name in SYNC_FILES:
        p = base / name
        if p.is_file():
            files[name] = sha256_file(p)
    for d in SYNC_DIRS:
        top = base / d
        if not top.is_dir():
            continue
        for p in top.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(base)
            if is_excluded(rel):
                continue
            files[rel.as_posix()] = sha256_file(p)
    return files


def main():
    parser = argparse.ArgumentParser(description="Sync skill files to target directory with hash verification.")
    parser.add_argument("--target", default=None, help="Target skill directory path")
    parser.add_argument("--check", action="store_true", help="Check hash parity without writing")
    parser.add_argument("--prune", action="store_true",
                        help="Sync mode only: delete extra files in the target that are inside synced items")
    args = parser.parse_args()

    if args.check and args.prune:
        parser.error("--prune cannot be combined with --check (--check never writes or deletes)")

    if args.target:
        target = Path(args.target).resolve()
    elif args.check:
        target = Path.home() / ".gemini" / "config" / "skills" / "orchestrator-supervisor-reviewer"
    else:
        parser.error("--target is required in sync mode (no default path write)")

    src_files = collect(ROOT)

    if args.check:
        if not target.exists():
            print("ERROR: target directory does not exist: %s" % target, file=sys.stderr)
            sys.exit(1)
        tgt_files = collect(target)
        missing = sorted(r for r in src_files if r not in tgt_files)
        differing = sorted(r for r in src_files if r in tgt_files and tgt_files[r] != src_files[r])
        extra = sorted(r for r in tgt_files if r not in src_files)
        if missing or differing or extra:
            print("Sync check failed:", file=sys.stderr)
            for m in missing:
                print("  missing: %s" % m, file=sys.stderr)
            for d in differing:
                print("  differs: %s" % d, file=sys.stderr)
            for e in extra:
                print("  extra: %s" % e, file=sys.stderr)
            sys.exit(1)
        print("Check OK: all %d files match target hashes at %s" % (len(src_files), target))
        sys.exit(0)

    target.mkdir(parents=True, exist_ok=True)
    synced_count = 0
    for rel in sorted(src_files):
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
        synced_count += 1

    mismatches = [rel for rel, h in src_files.items() if sha256_file(target / rel) != h]
    if mismatches:
        print("ERROR: Post-sync hash mismatch on %d files:" % len(mismatches), file=sys.stderr)
        for m in mismatches:
            print("  - %s" % m, file=sys.stderr)
        sys.exit(1)

    extras = sorted(r for r in collect(target) if r not in src_files)
    if args.prune:
        for rel in extras:
            (target / rel).unlink()
            print("pruned: %s" % rel)
    elif extras:
        for rel in extras:
            print("kept extra (use --prune to delete): %s" % rel)

    print("Successfully synced %d files to %s with 100%% hash parity verified." % (synced_count, target))


if __name__ == "__main__":
    main()
