#!/usr/bin/env python3
"""Git pre-commit hook verifying OSR evidence and staged-artifact parity.

The hook is deliberately read-only. It asks the OSR CLI for a read-only
``audit --check`` verdict, then compares the *complete* proposed index with the
audited working tree using NUL-safe Git plumbing. It never stages, repairs,
refreshes, or rewrites anything, and it never runs a configured test command.

Parity rule: exact bytes always pass. Otherwise only a pure CRLF/LF difference
is accepted, and only when Git's real text treatment for the path says the
repository stores normalized text. ``-text``/``binary`` explicitly opt out even
when ``core.autocrlf`` is enabled. Unsupported clean filters and
``working-tree-encoding`` transformations fail with a diagnostic instead of
being silently accepted. This local equivalence is not proof that another
checkout or platform reproduces the same baseline bytes; that remains
UNVERIFIED until integration/CI exercises it.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ERROR_PREFIX = "PRE-COMMIT ERROR:"
GOVERNANCE_ROOT = ".ai"
ESSENTIAL_GOVERNANCE = (
    ".ai/PLAN.md",
    ".ai/config.json",
    ".ai/state.json",
    ".ai/ledger.jsonl",
)
SUPPORTED_INDEX_MODES = ("100644", "100755")
AUDIT_TIMEOUT_SECONDS = 600

# Mirror scripts/osr.py DEFAULT_CFG["ignore"] for the fallback case where the
# config cannot be read. The successful audit already proves the real config is
# usable, but the hook still fails closed if the policy disappears.
DEFAULT_IGNORE = [
    ".git", ".ai", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "venv", ".venv", "env", "dist", "build", "target", ".next",
    ".nuxt", ".cache", "coverage", ".idea", ".vscode", ".DS_Store", "*.pyc",
    "*.pyo", "*.log", ".gradle", "bin", "obj", ".tox", ".terraform",
]

AUTOCRLF_TEXT_VALUES = ("true", "input", "1", "yes", "on")
UNSET_ATTRIBUTE_VALUES = (None, "unspecified", "unset")


def path_key(rel):
    """Canonical identity for one repository-relative path.

    Governance classification, ignore filtering, required-file membership,
    attribute lookup and case-collision detection all use this single
    identity. A differently cased spelling therefore cannot satisfy one check
    while escaping another on a case-insensitive filesystem.
    """
    return os.path.normcase(rel.replace("/", os.sep))


GOVERNANCE_KEY = path_key(GOVERNANCE_ROOT)
GIT_KEY = path_key(".git")


def fail(message):
    sys.stderr.write("%s %s\n" % (ERROR_PREFIX, message))
    raise SystemExit(1)


def git_env():
    """Environment that forbids optional index writes in child Git commands."""
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def decode(raw):
    return raw.decode("utf-8", "replace")


def run_git(root, args, input_bytes=None):
    """Run one read-only Git plumbing command and return raw stdout."""
    try:
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=str(root),
            input=input_bytes,
            capture_output=True,
            env=git_env(),
            timeout=120,
        )
    except FileNotFoundError:
        fail("git is not available; the staged artifact cannot be verified.")
    except subprocess.TimeoutExpired:
        fail("git %s timed out while reading the index." % " ".join(args[:3]))
    if proc.returncode != 0:
        detail = decode(proc.stderr or proc.stdout or b"").strip()
        fail("git %s failed (exit %d): %s" % (" ".join(args[:3]), proc.returncode, detail))
    return proc.stdout


def read_core_autocrlf(root):
    """Read Git's effective core.autocrlf without touching repository config."""
    try:
        proc = subprocess.run(
            ["git", "config", "--get", "core.autocrlf"],
            cwd=str(root),
            capture_output=True,
            env=git_env(),
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode == 0:
        return decode(proc.stdout).strip().lower()
    if proc.returncode == 1:
        return ""
    fail("git config --get core.autocrlf failed (exit %d): %s" % (
        proc.returncode, decode(proc.stderr).strip(),
    ))


def resolve_tooling(root):
    """Return the command prefix for a usable OSR CLI, or None."""
    local = root / "scripts" / "osr.py"
    if local.is_file():
        return [sys.executable, str(local)]

    # The helper is documented at integrations/git/pre_commit.py or
    # .git/hooks/pre_commit.py; both are three levels below the project root.
    # Only accept those known layouts so an unrelated scripts/osr.py higher up
    # the filesystem can never become enforcement by accident.
    helper = Path(__file__).resolve()
    if len(helper.parents) >= 3 and (
        (helper.parent.name == "git" and helper.parent.parent.name == "integrations")
        or (helper.parent.name == "hooks" and helper.parent.parent.name == ".git")
    ):
        bundled = helper.parents[2] / "scripts" / "osr.py"
        if bundled.is_file():
            return [sys.executable, str(bundled)]

    external = shutil.which("osr")
    if external:
        return [external]
    return None


def audit_workflow(root, tool_command):
    """Require audit --check to exit 0 on the current working artifact."""
    command = list(tool_command) + ["--root", str(root), "audit", "--check"]
    try:
        proc = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=git_env(),
            timeout=AUDIT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        fail("the resolved OSR tooling could not be executed; refusing the commit.")
    except subprocess.TimeoutExpired:
        fail("osr audit --check timed out; refusing the commit.")
    if proc.returncode == 0:
        return
    output = ((proc.stdout or "") + (proc.stderr or "")).strip()
    fail(
        "osr audit --check rejected the current working artifact (exit %d):\n%s"
        % (proc.returncode, output or "(no diagnostic output)")
    )


def load_ignore_policy(root):
    cfg_path = root / GOVERNANCE_ROOT / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return list(DEFAULT_IGNORE)
    patterns = cfg.get("ignore") if isinstance(cfg, dict) else None
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        return list(DEFAULT_IGNORE)
    return patterns


def ignored_name(name, patterns):
    # osr.walk_tree matches one path component with fnmatch.fnmatch, which
    # case-normalizes on Windows only. Compare through path_key so the hook and
    # the audited tree share one identity policy on every platform.
    key = path_key(name)
    return any(fnmatch.fnmatchcase(key, path_key(pattern)) for pattern in patterns)


def is_ignored_path(rel, patterns):
    return any(ignored_name(part, patterns) for part in rel.split("/"))


def is_governance(rel):
    key = path_key(rel)
    return key == GOVERNANCE_KEY or key.startswith(GOVERNANCE_KEY + os.sep)


def walk_working_tree(root, patterns):
    """Relative path -> actual on-disk path for every governed working file."""
    files = {}
    for dirpath, dirnames, filenames in os.walk(str(root)):
        # Governance and Git internals are handled separately and are never
        # part of the governed manifest. Identity is case-normalized on the
        # platforms where the filesystem is, matching path_key everywhere else.
        dirnames[:] = [
            name for name in dirnames
            if path_key(name) not in (GIT_KEY, GOVERNANCE_KEY)
            and not ignored_name(name, patterns)
        ]
        for name in filenames:
            if path_key(name) in (GIT_KEY, GOVERNANCE_KEY) or ignored_name(name, patterns):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            if is_governance(rel):
                continue
            files[path_key(rel)] = rel
    return files


def index_entries(root):
    """Parse ``git ls-files --stage -z`` without depending on the shell."""
    raw = run_git(root, ["ls-files", "--stage", "-z"])
    entries = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, separator, path_bytes = record.partition(b"\t")
        if not separator:
            fail("unexpected git ls-files output; cannot verify the complete index.")
        parts = decode(meta).split()
        if len(parts) != 3:
            fail("unexpected git ls-files entry for %r; cannot verify the complete index."
                 % os.fsdecode(path_bytes))
        mode, oid, stage = parts
        entries.append((mode, oid, stage, os.fsdecode(path_bytes)))
    return entries


def read_index_blobs(root, object_ids):
    """Read raw index blobs in one batch; filters are never applied."""
    ordered = sorted(set(object_ids))
    if not ordered:
        return {}
    request = ("\n".join(ordered) + "\n").encode("ascii")
    raw = run_git(root, ["cat-file", "--batch"], input_bytes=request)
    blobs = {}
    position = 0
    for oid in ordered:
        newline = raw.find(b"\n", position)
        if newline < 0:
            fail("git cat-file produced a truncated response for %s." % oid)
        header = decode(raw[position:newline]).split()
        position = newline + 1
        if len(header) == 2 and header[1] == "missing":
            fail("index object %s is missing from the object database." % oid)
        if len(header) != 3:
            fail("git cat-file returned an unexpected header for %s: %r"
                 % (oid, " ".join(header)))
        got_oid, object_type, size_text = header
        if got_oid != oid:
            fail("git cat-file returned %s while reading %s." % (got_oid, oid))
        if object_type != "blob":
            fail("index object %s is a %s, not a blob." % (oid, object_type))
        try:
            size = int(size_text)
        except ValueError:
            fail("git cat-file returned an invalid size for %s." % oid)
        end = position + size
        if end > len(raw):
            fail("git cat-file truncated blob %s." % oid)
        blobs[oid] = raw[position:end]
        position = end + 1  # the batch protocol terminates each object with LF
    return blobs


def read_attributes(root, paths):
    """Read real Git attributes without running filters or external commands."""
    unique = sorted(set(paths))
    if not unique:
        return {}
    payload = b"\0".join(os.fsencode(path) for path in unique) + b"\0"
    raw = run_git(root, ["check-attr", "-z", "--stdin", "-a"], input_bytes=payload)
    fields = raw.split(b"\0")
    attributes = {}
    index = 0
    while index + 2 < len(fields):
        path = os.fsdecode(fields[index])
        name = decode(fields[index + 1])
        value = decode(fields[index + 2])
        if not path:
            break
        attributes.setdefault(path_key(path), {})[name] = value
        index += 3
    return attributes


def is_binary(data):
    # Git's own heuristic: NUL in the first 8000 bytes means binary.
    return b"\0" in data[:8000]


def unsupported_transformation(attributes):
    filter_value = attributes.get("filter")
    if filter_value not in UNSET_ATTRIBUTE_VALUES:
        return "unsupported clean filter %r" % filter_value
    encoding = attributes.get("working-tree-encoding")
    if encoding not in UNSET_ATTRIBUTE_VALUES:
        return "unsupported working-tree-encoding %r" % encoding
    ident = attributes.get("ident")
    if ident not in UNSET_ATTRIBUTE_VALUES:
        return "unsupported ident attribute %r" % ident
    return None


def is_text_treatment(attributes, autocrlf, index_bytes, working_bytes):
    """Return (is_text, reason) for Git's effective treatment of one path."""
    text = attributes.get("text")
    if attributes.get("binary") == "set":
        text = "unset"
    if text in ("unset", "false"):
        return False, "the path is explicitly -text/binary"
    if text not in (None, "set", "true", "auto"):
        return False, "unsupported text attribute value %r" % text

    eol = attributes.get("eol")
    crlf = attributes.get("crlf")
    explicit_text = (
        text in ("set", "true", "auto")
        or eol in ("crlf", "lf")
        or crlf in ("set", "true", "input")
    )
    if explicit_text:
        if text == "auto" and (is_binary(index_bytes) or is_binary(working_bytes)):
            return False, "text=auto treats the content as binary (NUL byte)"
        return True, ""
    if autocrlf in AUTOCRLF_TEXT_VALUES:
        if is_binary(index_bytes) or is_binary(working_bytes):
            return False, "core.autocrlf is set but the content is binary (NUL byte)"
        return True, ""
    return False, "Git does not treat the path as text (no text attribute and core.autocrlf is off)"


def has_bare_carriage_return(data):
    return b"\r" in data.replace(b"\r\n", b"")


def compare_bytes(index_bytes, working_bytes, attributes, autocrlf):
    """Return (ok, reason) for the index-versus-working parity rule."""
    reason = unsupported_transformation(attributes)
    if reason:
        return False, reason
    if index_bytes == working_bytes:
        return True, ""
    is_text, reason = is_text_treatment(attributes, autocrlf, index_bytes, working_bytes)
    if not is_text:
        return False, reason
    if has_bare_carriage_return(index_bytes) or has_bare_carriage_return(working_bytes):
        return False, "the difference includes a bare carriage return"
    if index_bytes.replace(b"\r\n", b"\n") != working_bytes.replace(b"\r\n", b"\n"):
        return False, "the difference is not confined to CRLF/LF line endings"
    return True, ""


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def required_governance(root):
    """Essential files plus current cards and their referenced reviews."""
    required = set(ESSENTIAL_GOVERNANCE)
    tasks_dir = root / GOVERNANCE_ROOT / "tasks"
    task_ids = set()
    if tasks_dir.is_dir():
        for card in sorted(tasks_dir.glob("*.md")):
            if card.is_file():
                task_ids.add(card.stem)
                required.add(card.relative_to(root).as_posix())

    state = load_json(root / GOVERNANCE_ROOT / "state.json")
    state_tasks = state.get("tasks") if isinstance(state, dict) else None
    if not isinstance(state_tasks, dict):
        state_tasks = {}

    ledger_path = root / GOVERNANCE_ROOT / "ledger.jsonl"
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict) or entry.get("type") != "review":
            continue
        task = entry.get("task")
        if task not in task_ids:
            continue
        attempt = entry.get("attempt")
        current = state_tasks.get(task)
        if isinstance(current, dict) and current.get("attempts") != attempt:
            continue
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        stage = data.get("stage")
        if stage not in ("spec", "quality"):
            continue
        required.add("%s/reviews/%s.%s.md" % (GOVERNANCE_ROOT, task, stage))
    return required


def read_working_bytes(root, rel):
    try:
        return (root / rel).read_bytes()
    except OSError as exc:
        fail("cannot read the audited working file %s: %s" % (rel, exc))


def verify_complete_index(root):
    patterns = load_ignore_policy(root)
    autocrlf = read_core_autocrlf(root)

    entries = index_entries(root)
    index_by_key = {}
    index_governance = []
    for mode, oid, stage, rel in entries:
        if stage != "0":
            fail("unsupported merge stage %s for %s; resolve the conflict first."
                 % (stage, rel))
        if mode not in SUPPORTED_INDEX_MODES:
            fail("unsupported index mode %s for %s; only regular files can be verified."
                 % (mode, rel))
        key = path_key(rel)
        if key in index_by_key and index_by_key[key][0] != rel:
            fail("case-colliding index paths %s and %s cannot both be verified."
                 % (index_by_key[key][0], rel))
        index_by_key[key] = (rel, oid)
        if is_governance(rel):
            index_governance.append(rel)

    blobs = read_index_blobs(root, [oid for _, oid in index_by_key.values()])
    working = walk_working_tree(root, patterns)
    required = required_governance(root)

    attribute_paths = set(required)
    attribute_paths.update(rel for rel, _ in index_by_key.values())
    attribute_paths.update(working.values())
    attributes = read_attributes(root, attribute_paths)

    # Every governed path in the audited working artifact must have exactly
    # those bytes in the proposed index (subject only to the text rule).
    for key, (rel, oid) in sorted(index_by_key.items()):
        if is_governance(rel) or is_ignored_path(rel, patterns):
            continue
        if key not in working:
            fail("index-only governed path %s is absent from the audited working tree." % rel)
        working_rel = working[key]
        ok, reason = compare_bytes(
            blobs[oid],
            read_working_bytes(root, working_rel),
            attributes.get(path_key(rel), {}),
            autocrlf,
        )
        if not ok:
            fail("staged bytes for governed path %s cannot be verified: %s." % (rel, reason))

    for key, rel in sorted(working.items()):
        if key not in index_by_key:
            fail("governed file %s is present in the audited working tree but is not staged." % rel)

    # Governance is outside the governed manifest, so it needs its own
    # essential/current-artifact comparison. Optional generated reports and
    # logs are not required, but anything indexed must not silently carry stale
    # bytes. Required membership, classification and comparison all use
    # path_key, so a differently cased spelling cannot satisfy the
    # required-file check and then escape this byte comparison.
    required_by_key = {path_key(rel): rel for rel in required}
    for rel in sorted(index_governance):
        key = path_key(rel)
        canonical = required_by_key.get(key, rel)
        disk_path = root / canonical
        if key in required_by_key and not disk_path.is_file():
            fail("required governance file %s is missing from the audited working tree."
                 % canonical)
        if key not in required_by_key and not disk_path.is_file():
            fail("index-only governance path %s is absent from the audited working tree." % rel)
        ok, reason = compare_bytes(
            blobs[index_by_key[key][1]],
            read_working_bytes(root, canonical),
            attributes.get(key, {}),
            autocrlf,
        )
        if not ok:
            fail("staged governance bytes for %s differ from the audited working evidence: %s."
                 % (rel, reason))

    for rel in sorted(required):
        if path_key(rel) not in index_by_key:
            fail("required governance file %s is missing from the proposed index." % rel)


def main():
    root = Path.cwd()
    workflow = root / GOVERNANCE_ROOT
    if not workflow.is_dir():
        # A repository with no OSR workflow is permitted, whether or not some
        # unrelated tooling happens to be installed.
        return 0

    tool_command = resolve_tooling(root)
    if not tool_command:
        fail(
            "an initialized .ai workflow has no usable OSR tooling; looked for "
            "scripts/osr.py, helper-relative scripts/osr.py and an 'osr' CLI on PATH."
        )

    audit_workflow(root, tool_command)
    verify_complete_index(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
