#!/usr/bin/env python3
"""osr - Orchestrator-Supervisor-Reviewer enforcement CLI.

Python 3.8+, standard library only, works on Linux, macOS and Windows.

Principle: the AI proposes, this tool decides. Nothing the AI says counts as
evidence. Evidence is produced here (command output, file hashes, diffs against a
snapshot, parsed review files) and appended to a hash-chained ledger.

Run `osr next` at any time to see the single next required action.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

VERSION = "0.3.1"
ROOT = Path.cwd()
SCRIPT_DIR = Path(__file__).resolve().parent
ASSETS = SCRIPT_DIR.parent / "assets"
ZERO = "0" * 64
LAYERS = ["spec", "plan", "prompt", "context", "environment", "model", "implementation"]

EXIT_OK = 0
EXIT_USER_ERR = 1
EXIT_GATE_FAIL = 2
EXIT_BLOCKED = 3
EXIT_INTEGRITY = 4

DEFAULT_CFG = {
    "version": 1,
    "max_attempts": 3,
    "max_inner_failures": 2,
    "task_card_max_lines": 150,
    "context_budget_lines": 1500,
    "command_timeout_seconds": 600,
    "max_scan_bytes": 2000000,
    "max_files": 30000,
    "require_distinct_reviewer": False,
    "allow_no_commands": False,
    "allow_broad_scope": False,
    "human_only_flags": ["tests-weakened", "skips-added", "secret", "unanchored-mock"],
    "env_smoke": ["build", "typecheck", "lint"],
    "ignore": [
        ".git", ".ai", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", "venv", ".venv", "env", "dist", "build", "target", ".next",
        ".nuxt", ".cache", "coverage", ".idea", ".vscode", ".DS_Store", "*.pyc",
        "*.pyo", "*.log", ".gradle", "bin", "obj", ".tox", ".terraform",
    ],
    "commands": {},
    "global_verify": [],
    "extra_placeholder_patterns": [],
    "checkers": [],
}

PLACEHOLDER_PATTERNS = [
    r"rest of (the )?(existing )?(code|file|function|class|implementation)",
    r"(existing|previous|remaining|other) (code|implementation|methods?|logic) (here|remains|unchanged|stays)",
    r"\.\.\.\s*(existing|rest of|remaining|same as)",
    r"\bTODO\b[: ]+(implement|add|fill|write)",
    r"your (code|implementation|logic) (goes )?here",
    r"pass\s*#\s*(todo|implement|placeholder|stub)",
    r"raise NotImplementedError",
    r"throw new Error\(['\"]not implemented",
    r"^\s*(//|#)\s*\.\.\.\s*$",
]
SECRET_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    r"ghp_[A-Za-z0-9]{36}",
    r"sk-[A-Za-z0-9]{32,}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}",
]
BOGUS_SOURCE_PAT = re.compile(
    r"(?:^|[/\\])(?:mocks?|fixtures?|stubs?|tests?|fakes?)(?:[/\\]|$)|(?:^|[/\\])(?:mock_|fake_|stub_|test_)[^/\\]+$|\.(?:mock|stub|fake|test|spec)\.[^/\\]+$",
    re.I,
)


def is_mock_or_test_source(path_str):
    if not path_str:
        return False
    clean = path_str.strip().replace("\\", "/")
    return bool(BOGUS_SOURCE_PAT.search(clean))


TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|specs?)/|(^|/)test_[^/]*$|[^/]*(_test|\.test|\.spec|_spec)\.[^/]+$|[^/]*Tests?\.(java|kt|cs|swift)$"
)
ASSERT_RE = re.compile(
    r"\bassert\w*\b|\bexpect\s*\(|\.should\b|\bt\.(Error|Fatal|Equal)\w*|\bXCTAssert\w*|\bAssert\.\w+|\bself\.assert\w+"
)
SKIP_RE = re.compile(
    r"@pytest\.mark\.(skip|xfail)|\bpytest\.skip\b|@unittest\.skip|\b(it|test|describe)\.(skip|only)\b|"
    r"\bx(it|describe|test)\s*\(|\bt\.Skip\w*\(|@Disabled|@Ignore|\.only\s*\("
)
NO_TESTS = re.compile(
    r"(collected 0 items|no tests ran|no tests found|no test files|ran 0 tests|\b0 tests? (passed|run|found|executed)|"
    r"no tests to run|tests:\s+0 total|\b0 passing|test suites?:\s*0 total)",
    re.I,
)
TRIVIAL_CMD = re.compile(r"^\s*(echo|true|exit\s+0|:|printf|print)\b", re.I)
WEAK_VERIFY_PAT = re.compile(
    r"(\bgrep\b|\bfindstr\b|\bSelect-String\b|-c\s+[\"'].*?(?:in\s+pathlib|sys\.exit|import\s+pathlib))",
    re.I,
)
CODE_EXTS = {
    ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".scala", ".dart", ".ex", ".exs", ".lua", ".sh", ".ps1", ".vue", ".svelte", ".r", ".jl", ".zig",
}
JS_EXTS = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
JS_TAUTOLOGY_RE = [
    re.compile(r"expect\s*\(\s*([a-zA-Z0-9_$.]+)\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)"),
    re.compile(r"""expect\s*\(\s*(true|false|\d+|"[^"]*"|'[^']*')\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)"""),
    re.compile(r"assert\s*\.\s*(equal|strictEqual|deepEqual)\s*\(\s*([a-zA-Z0-9_$.]+)\s*,\s*\2\s*\)"),
]


def scan_tautological_python(path, text):
    findings = []
    try:
        tree = ast.parse(text, filename=str(path))
    except Exception:
        return findings

    def is_const(n):
        if isinstance(n, ast.Constant):
            return True
        if hasattr(ast, "Num") and isinstance(n, (ast.Num, ast.Str, ast.NameConstant)):
            return True
        return False

    def same_node(n1, n2):
        if type(n1) is not type(n2):
            return False
        if isinstance(n1, ast.Name):
            return n1.id == n2.id
        if isinstance(n1, ast.Constant):
            return n1.value == n2.value
        if hasattr(ast, "Num") and isinstance(n1, ast.Num):
            return n1.n == n2.n
        if hasattr(ast, "Str") and isinstance(n1, ast.Str):
            return n1.s == n2.s
        if hasattr(ast, "NameConstant") and isinstance(n1, ast.NameConstant):
            return n1.value == n2.value
        if isinstance(n1, ast.Attribute):
            return n1.attr == n2.attr and same_node(n1.value, n2.value)
        try:
            return ast.dump(n1) == ast.dump(n2)
        except Exception:
            return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            t = node.test
            if is_const(t) and bool(getattr(t, "value", True)):
                findings.append((node.lineno, "Python AST: constant assertion"))
            elif isinstance(t, ast.Compare):
                for op, comp in zip(t.ops, t.comparators):
                    if isinstance(op, (ast.Eq, ast.Is)):
                        if same_node(t.left, comp):
                            findings.append((node.lineno, "Python AST: self-comparison assertion"))
                        elif is_const(t.left) and is_const(comp):
                            findings.append((node.lineno, "Python AST: constant comparison assertion"))
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name in ("assertEqual", "assertIs", "assert_equal"):
                if len(node.args) >= 2:
                    if same_node(node.args[0], node.args[1]):
                        findings.append((node.lineno, "Python AST: %s self-comparison" % name))
                    elif is_const(node.args[0]) and is_const(node.args[1]):
                        findings.append((node.lineno, "Python AST: %s with constant literals" % name))
            elif name in ("assertTrue", "assertFalse"):
                if len(node.args) >= 1 and is_const(node.args[0]):
                    val = getattr(node.args[0], "value", None)
                    if (name == "assertTrue" and bool(val) is True) or (name == "assertFalse" and bool(val) is False):
                        findings.append((node.lineno, "Python AST: %s with constant literal" % name))
    return findings


def scan_tautological_js(path, text):
    findings = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, 1):
        for pat in JS_TAUTOLOGY_RE:
            if pat.search(line):
                findings.append((idx, "heuristic JS tautological assertion: %s" % line.strip()[:60]))
                break
    return findings
NODE_BUILTINS = set(
    "assert async_hooks buffer child_process cluster console constants crypto dgram diagnostics_channel dns "
    "domain events fs http http2 https inspector module net os path perf_hooks process punycode querystring "
    "readline repl stream string_decoder sys timers tls trace_events tty url util v8 vm wasi worker_threads zlib".split()
)
QUALITY_CHECKS = {
    "C1": "references exist (imports, APIs, files, config keys, env vars)",
    "C2": "error handling and edge cases",
    "C3": "security (input validation, secrets, injection, authorization)",
    "C4": "no placeholders, stubs, truncation, or leftover dead code",
    "C5": "no regressions in untouched behavior (callers, interfaces, contracts)",
    "C6": "tests are meaningful (assert behavior, not weakened, not skipped)",
    "C7": "consistent with existing code conventions",
    "C8": "scope respected, no unrelated changes",
}


# ----------------------------------------------------------------------------- basics
def ai(*p):
    return ROOT.joinpath(".ai", *p)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha_text(s):
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def join_arg(val):
    if isinstance(val, (list, tuple)):
        return " ".join(val)
    return str(val) if val is not None else ""


JSON_MODE = False


def emit_json(payload, code=0):
    if "exit_code" not in payload:
        payload["exit_code"] = code
    if "ok" not in payload:
        payload["ok"] = (code == 0)
    print(json.dumps(payload, indent=2))
    sys.exit(code)


def die(msg, code=1):
    if JSON_MODE:
        status_map = {1: "error", 2: "gate_failed", 3: "blocked", 4: "integrity_violation"}
        emit_json({"ok": False, "exit_code": code, "error": msg, "status": status_map.get(code, "error")}, code=code)
    print(msg, file=sys.stderr)
    sys.exit(code)


_LOCK_DEPTH = 0


class LedgerLock:
    def __init__(self, timeout=0.3):
        self.lock = ai(".ledger.lock")
        self.timeout = timeout
        self.acquired = False

    def __enter__(self):
        global _LOCK_DEPTH
        if _LOCK_DEPTH > 0:
            _LOCK_DEPTH += 1
            return self
        start = time.time()
        while True:
            try:
                self.lock.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(self.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, ("pid=%d ts=%f\n" % (os.getpid(), time.time())).encode("utf-8"))
                os.close(fd)
                self.acquired = True
                _LOCK_DEPTH = 1
                return self
            except FileExistsError:
                if (time.time() - start) >= self.timeout:
                    die("Ledger lock is held (%s). Another process is writing or a previous run crashed." % self.lock, code=1)
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _LOCK_DEPTH
        if _LOCK_DEPTH > 1:
            _LOCK_DEPTH -= 1
            return
        _LOCK_DEPTH = 0
        if self.acquired and self.lock.exists():
            try:
                self.lock.unlink()
            except OSError:
                pass


def load_cfg():
    p = ai("config.json")
    if not p.exists():
        die("Not initialized. Run: osr init")
    cfg = dict(DEFAULT_CFG)
    cfg.update(json.loads(p.read_text(encoding="utf-8")))
    return cfg


def save_cfg(cfg):
    ai("config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def sha_config():
    p = ai("config.json")
    if not p.exists():
        return ZERO
    try:
        cfg_obj = json.loads(p.read_text(encoding="utf-8"))
        return sha_text(json.dumps(cfg_obj, sort_keys=True))
    except Exception:
        return sha_text(p.read_text(encoding="utf-8"))


def ensure_plan_and_config_approved(st):
    if st.get("plan_hash") != sha_text(ai("PLAN.md").read_text(encoding="utf-8")):
        die("PLAN.md is not approved or changed since approval. The human must run: osr approve-plan --by <name>")
    if st.get("config_hash") and st["config_hash"] != sha_config():
        die("config.json has changed since plan approval. The human must re-run approve-plan to approve the updated configuration.", code=EXIT_INTEGRITY)


def ensure_approval_fresh(st):
    """Reject changed approved inputs only when a prior approval was recorded.

    Quick verify and fixture capture intentionally work without an active task,
    so a project that has never recorded a plan/config approval keeps its
    existing exact-command behavior. Once the human has bound an approval,
    later edits to PLAN.md or config.json make that approval stale until the
    human re-runs approve-plan. Reconfirming a command proves command identity;
    it never invents approval or refreshes these hashes.
    """
    approved_plan = st.get("plan_hash")
    approved_config = st.get("config_hash")
    if not approved_plan and not approved_config:
        return
    if approved_plan:
        plan_path = ai("PLAN.md")
        current_plan = sha_text(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
        if approved_plan != current_plan:
            die("PLAN.md is not approved or changed since approval. The human must run: osr approve-plan --by <name>")
    if approved_config and approved_config != sha_config():
        die("config.json has changed since plan approval. The human must re-run approve-plan to approve the updated configuration.", code=EXIT_INTEGRITY)


def check_approval_secret(cfg, a):
    expected_sha = cfg.get("approval_secret_sha")
    if not expected_sha:
        return
    provided = getattr(a, "secret", None) or os.environ.get("OSR_APPROVAL_SECRET")
    if not provided:
        die("An approval secret is configured in config.json. You must provide --secret <secret> or set OSR_APPROVAL_SECRET.", code=EXIT_USER_ERR)
    h = hashlib.sha256(provided.encode("utf-8")).hexdigest()
    if h != expected_sha:
        die("Invalid approval secret provided.", code=EXIT_USER_ERR)


def load_state():
    p = ai("state.json")
    if not p.exists():
        return {"plan_hash": None, "config_hash": None, "tasks": {}, "waivers": [], "signoffs": {}, "fixtures": {}}
    st = json.loads(p.read_text(encoding="utf-8"))
    st.setdefault("fixtures", {})
    return st


def save_state(st):
    ai("state.json").write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")


def task_state(st, tid):
    return st["tasks"].setdefault(
        tid,
        {
            "status": "todo", "attempts": 0, "failures": 0, "model": None, "input_hash": None,
            "triaged_attempt": 0, "blocked": None, "requires": None, "extra_attempts": 0,
        },
    )


# ----------------------------------------------------------------------------- ledger
class Ledger:
    def __init__(self):
        self.path = ai("ledger.jsonl")

    def entries(self):
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def verify_chain(self, anchor_path=None):
        prev = ZERO
        entries = self.entries()
        for i, e in enumerate(entries):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev") != prev:
                return False, "ledger entry %d: broken chain" % (i + 1)
            if sha_text(prev + json.dumps(body, sort_keys=True)) != e.get("hash"):
                return False, "ledger entry %d: content was modified" % (i + 1)
            prev = e["hash"]

        target_anchor = anchor_path if anchor_path is not None else (ROOT / ".osr-anchor")
        if anchor_path is not None and not target_anchor.exists():
            return False, "ledger anchor file does not exist: %s" % target_anchor

        if target_anchor.exists():
            try:
                raw = target_anchor.read_text(encoding="utf-8").strip()
                if raw.startswith("{"):
                    ainfo = json.loads(raw)
                    aseq = ainfo.get("seq")
                    ahash = ainfo.get("head_hash") or ainfo.get("hash")
                else:
                    aseq = None
                    ahash = raw
                if aseq is not None:
                    if len(entries) < aseq or entries[aseq - 1]["hash"] != ahash:
                        return False, "ledger anchor mismatch: rollback detected (expected seq %s with hash %s)" % (aseq, ahash)
                elif ahash:
                    if not any(e["hash"] == ahash for e in entries):
                        return False, "ledger anchor mismatch: anchored hash %s missing from ledger" % ahash
            except Exception as ex:
                return False, "ledger anchor verification failed: %s" % ex

        return True, "ok"

    def append(self, typ, task=None, attempt=None, **data):
        with LedgerLock(timeout=0.3):
            es = self.entries()
            prev = es[-1]["hash"] if es else ZERO
            body = {"seq": len(es) + 1, "ts": now(), "type": typ, "task": task, "attempt": attempt, "data": data, "prev": prev}
            body["hash"] = sha_text(prev + json.dumps(body, sort_keys=True))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(body) + "\n")
            return body

    def latest(self, typ, task=None, attempt=None, stage=None):
        for e in reversed(self.entries()):
            if e["type"] != typ:
                continue
            if task is not None and e["task"] != task:
                continue
            if attempt is not None and e["attempt"] != attempt:
                continue
            if stage is not None and e["data"].get("stage") != stage:
                continue
            return e
        return None


def ctx(require_chain=True):
    cfg = load_cfg()
    st = load_state()
    led = Ledger()
    if require_chain:
        ok, msg = led.verify_chain()
        if not ok:
            die("LEDGER INTEGRITY FAILURE: %s\nThe ledger is append-only and written only by osr. Stop and tell the human." % msg, code=4)
    return cfg, st, led


# ----------------------------------------------------------------------------- globbing and tree
def glob_re(pat):
    pat = pat.replace("\\", "/")
    pat = re.sub(r"^\./", "", pat)
    if pat.endswith("/"):
        pat += "**"
    i, res = 0, ""
    while i < len(pat):
        if pat.startswith("**/", i):
            res += "(?:.*/)?"
            i += 3
            continue
        if pat.startswith("**", i):
            res += ".*"
            i += 2
            continue
        c = pat[i]
        res += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
        i += 1
    return re.compile("^" + res + "$")


def matches(path, pats):
    return any(glob_re(p).match(path) for p in pats)


def count(text, regs):
    return sum(len(r.findall(text)) for r in regs)


def compiled(cfg):
    ph = [re.compile(p, re.I | re.M) for p in PLACEHOLDER_PATTERNS + list(cfg.get("extra_placeholder_patterns", []))]
    sec = [re.compile(p) for p in SECRET_PATTERNS]
    return ph, sec


def file_info(path, rel, cfg, regs):
    ph, sec = regs
    st = path.stat()
    h = hashlib.sha256()
    info = {"size": st.st_size}
    if st.st_size > cfg["max_scan_bytes"]:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        info["sha"] = h.hexdigest()
        return info
    data = path.read_bytes()
    h.update(data)
    info["sha"] = h.hexdigest()
    if b"\0" in data[:8000]:
        info["binary"] = True
        return info
    text = data.decode("utf-8", "replace")
    info["lines"] = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    info["ph"] = count(text, ph)
    info["secrets"] = count(text, sec)
    if TEST_PATH.search(rel):
        info["test"] = True
        info["asserts"] = len(ASSERT_RE.findall(text))
        info["skips"] = len(SKIP_RE.findall(text))
    return info


def ignored(name, cfg):
    return any(fnmatch.fnmatch(name, p) for p in cfg["ignore"])


def walk_tree(cfg):
    regs = compiled(cfg)
    res = {}
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if not ignored(d, cfg)]
        for fn in fns:
            if ignored(fn, cfg):
                continue
            p = Path(dp) / fn
            rel = p.relative_to(ROOT).as_posix()
            try:
                res[rel] = file_info(p, rel, cfg, regs)
            except OSError:
                continue
            if len(res) > cfg["max_files"]:
                die("Tree has more than max_files=%d files; raise it or extend 'ignore' in .ai/config.json" % cfg["max_files"])
    return res


def diff_tree(snap, cur):
    ch = {}
    for p, i in cur.items():
        if p not in snap:
            ch[p] = "A"
        elif snap[p]["sha"] != i["sha"]:
            ch[p] = "M"
    for p in snap:
        if p not in cur:
            ch[p] = "D"
    return ch


def fingerprint(ch, cur):
    return sha_text("\n".join("%s %s %s" % (ch[p], p, cur[p]["sha"] if p in cur else "-") for p in sorted(ch)))


def snap_path(tid):
    return ai("snapshots", tid + ".json")


# ----------------------------------------------------------------------------- freshness manifests
COMPLETION_SCHEMA = "osr.completion.v1"
LEGACY_CLOSURE_SCHEMA = "osr.legacy-closure.v1"
# Every start written by the binding-aware implementation carries these keys.
# A start with none of them is genuine pre-feature history; a start with only
# some of them is malformed new-format evidence and must never fall back.
START_BINDING_KEYS = (
    "approval_epoch", "start_base_sha", "start_snapshot_sha",
    "plan_raw_sha", "config_sha", "ignore_sha", "card_sha",
)
_APPROVAL_BASELINE_KEYS = ("manifest_sha", "plan_raw_sha", "ignore_sha", "approval_epoch")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def file_sha(rel):
    """SHA-256 of a project file's raw bytes (no newline normalisation)."""
    p = Path(rel)
    if not p.is_absolute():
        p = ROOT / p
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest_from_tree(tree):
    """Convert a walk_tree result (or a saved snapshot) to ``path -> sha``."""
    return {path: info["sha"] for path, info in (tree or {}).items() if isinstance(info, dict) and info.get("sha")}


def manifest_digest(manifest):
    """Canonical digest of one governed path-to-content-hash map."""
    canon = {path: manifest[path] for path in sorted(manifest or {})}
    return sha_text(json.dumps(canon, sort_keys=True, separators=(",", ":")))


def ignore_digest(cfg):
    """Canonical digest of the governed-tree ignore policy."""
    return sha_text(json.dumps(sorted(cfg.get("ignore", [])), separators=(",", ":")))


def snapshot_map(tid):
    """The ``path -> sha`` map saved by ``osr start`` for this task, if readable."""
    p = snap_path(tid)
    if not p.exists():
        return None
    try:
        return manifest_from_tree(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def valid_sha(value):
    return isinstance(value, str) and bool(_HEX64.match(value))


def state_task(st, tid):
    return (st.get("tasks") or {}).get(tid) or {}


def task_delta(base_map, result_map):
    """Explicit delta between two governed maps; deletion is ``None``."""
    delta, changed = {}, {}
    for path in set(base_map) | set(result_map):
        before, after = base_map.get(path), result_map.get(path)
        if before == after:
            continue
        if after is None:
            delta[path] = None
            changed[path] = "D"
        else:
            delta[path] = after
            changed[path] = "A" if before is None else "M"
    return delta, changed


def work_fingerprint(changed, result_map):
    """The existing work fingerprint, recomputed from a real delta and result map."""
    return sha_text("\n".join(
        "%s %s %s" % (changed[p], p, result_map[p] if p in result_map else "-")
        for p in sorted(changed)
    ))


# ----------------------------------------------------------------------------- plan and cards
class Plan(dict):
    def __init__(self, reqs, seams=None):
        super().__init__(reqs)
        self.seams = seams or {}


def parse_plan():
    p = ai("PLAN.md")
    if not p.exists():
        return None, ["PLAN.md missing"]
    text = p.read_text(encoding="utf-8")
    errs = []
    sections, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            cur = m.group(1).strip().lower()
            sections[cur] = []
        elif cur:
            sections[cur].append(ln)
    for need in ("goal", "non-goals", "requirements"):
        if need not in sections or not "".join(sections[need]).strip():
            errs.append("PLAN.md: section '## %s' missing or empty" % need.title())
    reqs, cur_r = {}, None
    for ln in sections.get("requirements", []):
        m = re.match(r"^\s*[-*]\s*(R\d+[a-zA-Z]?)\s*:\s*(.+)$", ln)
        if m:
            if m.group(1) in reqs:
                errs.append("PLAN.md: duplicate requirement id %s" % m.group(1))
            cur_r = m.group(1)
            reqs[cur_r] = {"text": m.group(2).strip(), "ac": [], "check": None}
            continue
        if cur_r:
            m = re.match(r"^\s+[-*]\s*AC\s*:\s*(.+)$", ln)
            if m:
                reqs[cur_r]["ac"].append(m.group(1).strip())
            m = re.match(r"^\s+[-*]\s*Check\s*:\s*(\w+)", ln)
            if m:
                reqs[cur_r]["check"] = m.group(1).lower()
            m = re.match(r"^\s+[-*]\s*Script\s*:\s*(.+)$", ln)
            if m:
                reqs[cur_r]["script"] = m.group(1).strip()
    if not reqs:
        errs.append("PLAN.md: no requirements found (format: '- R1: text' then indented '- AC:' and '- Check: auto|manual')")
    for r, v in reqs.items():
        if not v["ac"]:
            errs.append("PLAN.md: %s has no '- AC:' acceptance criterion" % r)
        elif any(len(a) < 15 for a in v["ac"]):
            errs.append("PLAN.md: %s has an acceptance criterion shorter than 15 chars (be concrete and testable)" % r)
        if v["check"] not in ("auto", "manual"):
            errs.append("PLAN.md: %s needs '- Check: auto' or '- Check: manual'" % r)
        if v["check"] == "manual" and v.get("script"):
            sp = ROOT / v["script"]
            if not sp.exists():
                errs.append("PLAN.md: %s references script '%s' which does not exist" % (r, v["script"]))
    for key, lines in sections.items():
        if "open question" in key or "assumption" in key:
            for ln in lines:
                if re.match(r"^\s*[-*]\s*\[ \]", ln):
                    errs.append("PLAN.md: unresolved item under '%s': %s (resolve it with the human, then tick [x])" % (key, ln.strip()))
    seams = {}
    for ln in sections.get("seams", []):
        raw = ln.strip()
        if not raw or not raw.startswith("|"):
            continue
        parts = [p.strip() for p in raw.strip("|").split("|")]
        if len(parts) >= 4:
            sid = parts[0]
            if sid.lower() in ("seam id", "seam_id", "---") or sid.startswith(":-") or sid.startswith("-"):
                continue
            consumer = parts[1]
            provider = parts[2]
            source = parts[3]
            how = parts[4] if len(parts) > 4 else ""
            if is_mock_or_test_source(source):
                errs.append("PLAN.md: seam '%s' authoritative source '%s' points to a mock/test/fixture path; authoritative source must be provider production source or specification" % (sid, source))
            seams[sid] = {
                "consumer": consumer,
                "provider": provider,
                "source": source,
                "how": how,
            }
    return Plan(reqs, seams), errs


CARD_KEYS = ["id", "requirements", "depends_on", "allowed_files", "forbidden_files", "context_files", "verify", "seams", "fixtures", "conformance", "kind", "negative_tests"]
CARD_LIST_KEYS = ["requirements", "depends_on", "allowed_files", "forbidden_files", "context_files", "seams", "fixtures", "conformance", "negative_tests"]
CARD_HEADINGS = ["goal", "constraints", "do not", "definition of done"]


def task_ids():
    d = ai("tasks")
    if not d.exists():
        return []
    ids = [p.stem for p in d.glob("*.md")]
    return sorted(ids, key=lambda s: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)])


def parse_card(tid):
    p = ai("tasks", tid + ".md")
    text = p.read_text(encoding="utf-8")
    card = {k: [] for k in CARD_KEYS}
    for ln in text.splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?(%s)\s*:\s*(.+?)\s*$" % "|".join(CARD_KEYS), ln, re.I)
        if not m:
            continue
        k, v = m.group(1).lower(), m.group(2).strip().strip("`").strip()
        if k in CARD_LIST_KEYS:
            card[k] += [x.strip().strip("`") for x in v.split(",") if x.strip()]
        else:
            card[k].append(v)
    card["_text"] = text
    card["_lines"] = len(text.splitlines())
    heads = [re.sub(r"[^a-z ]", "", h.lower()).strip() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    card["_heads"] = heads
    return card


def normalize_command(cmd):
    """Authorization identity of one command: the exact string, outer whitespace trimmed.

    This is deliberately not a shell parser. Two commands are the same command
    only when their trimmed strings are identical; internal whitespace, quoting,
    case, arguments and shell suffixes all take part in the identity.
    """
    if cmd is None:
        return ""
    return str(cmd).strip()


def is_verify_cmd_confirmed(v_cmd, cfg, led=None):
    """Authorize exactly one outer-whitespace-trimmed, ledger-confirmed command.

    A candidate is authorized only when it equals the current exact command of a
    config entry whose newest ledger confirmation for that same command succeeded.
    Empty candidates, missing confirmations and unmatched commands are rejected.
    There is no executable, module, prefix, case or command-family equivalence.
    ``allow_no_commands`` stays the explicit compatibility escape: it permits
    execution but is never evidence that a command was confirmed.
    """
    if cfg.get("allow_no_commands"):
        return True
    if led is None:
        led = Ledger()
    candidate = normalize_command(v_cmd)
    if not candidate:
        return False
    for n in cfg.get("commands", {}):
        entry = cfg["commands"].get(n) or {}
        if normalize_command(entry.get("cmd")) != candidate:
            continue
        if confirmed(cfg, led, n):
            return True
    return False


def validate_card(tid, cfg, plan, strict_files=True):
    errs = []
    if not ai("tasks", tid + ".md").exists():
        return None, ["task card .ai/tasks/%s.md not found" % tid]
    c = parse_card(tid)
    if not c["id"] or c["id"][0] != tid:
        errs.append("%s: 'id:' line must exist and equal the file name (%s)" % (tid, tid))
    if not c["requirements"]:
        errs.append("%s: 'requirements:' missing" % tid)
    for r in c["requirements"]:
        if plan is not None and r not in plan:
            errs.append("%s: requirement %s does not exist in PLAN.md" % (tid, r))
    if not c["allowed_files"]:
        errs.append("%s: 'allowed_files:' missing (scope lock)" % tid)
    for g in c["allowed_files"]:
        if g.strip() in ("*", "**", "**/*", "./**", ".") and not cfg["allow_broad_scope"]:
            errs.append("%s: allowed_files '%s' is too broad; list the specific files or folders" % (tid, g))
    if not c["verify"]:
        errs.append("%s: needs at least one 'verify:' command that checks THIS task" % tid)
    for v in c["verify"]:
        if TRIVIAL_CMD.match(v):
            errs.append("%s: verify command '%s' cannot prove anything" % (tid, v))
        elif WEAK_VERIFY_PAT.search(v):
            errs.append("%s: verify command '%s' is a weak verify command (token existence check, not a test)" % (tid, v))
        elif not is_verify_cmd_confirmed(v, cfg):
            errs.append("%s: verify command '%s' is not confirmed (must match a confirmed command in .ai/config.json)" % (tid, v))
    for v in c.get("conformance", []):
        if v in cfg.get("commands", {}):
            if not confirmed(cfg, None, v):
                errs.append("%s: conformance command '%s' is not confirmed (must run: osr confirm-commands)" % (tid, v))
        else:
            if TRIVIAL_CMD.match(v):
                errs.append("%s: conformance command '%s' cannot prove anything" % (tid, v))
            elif not is_verify_cmd_confirmed(v, cfg):
                errs.append("%s: conformance command '%s' is not confirmed (must match a confirmed command in .ai/config.json)" % (tid, v))
    for h in CARD_HEADINGS:
        if h not in c["_heads"]:
            errs.append("%s: section '## %s' missing" % (tid, h.title()))
    if c["_lines"] > cfg["task_card_max_lines"]:
        errs.append("%s: card is %d lines (max %d); split the task" % (tid, c["_lines"], cfg["task_card_max_lines"]))
    total = c["_lines"]
    for f in c["context_files"]:
        fp = ROOT / f
        if not fp.exists():
            errs.append("%s: context file '%s' does not exist" % (tid, f))
        else:
            try:
                total += len(fp.read_text(encoding="utf-8", errors="replace").splitlines())
            except OSError:
                pass
    if total > cfg["context_budget_lines"]:
        errs.append("%s: context packet is %d lines (budget %d); trim context_files or split the task" % (tid, total, cfg["context_budget_lines"]))
    for d in c["depends_on"]:
        if d not in task_ids():
            errs.append("%s: depends_on '%s' is not a task" % (tid, d))
    if re.search(r"^\s*context_contracts\s*:", c.get("_text", ""), re.M | re.I):
        errs.append("%s: 'context_contracts' is not permitted; use 'context_files'" % tid)
    seams_dict = getattr(plan, "seams", {}) if plan is not None else {}
    for s in c.get("seams", []):
        if s not in seams_dict:
            errs.append("%s: seam '%s' is not declared in PLAN.md Seams table" % (tid, s))
        else:
            src = seams_dict[s].get("source", "").strip()
            if is_mock_or_test_source(src):
                errs.append("%s: seam '%s' authoritative source '%s' points to a mock/test/fixture path; authoritative source must be provider production source or specification" % (tid, s, src))
            normalized_cf = [Path(cf).as_posix() for cf in c["context_files"]]
            normalized_src = Path(src).as_posix() if src else ""
            if not normalized_src or normalized_src not in normalized_cf:
                errs.append("%s: seam '%s' authoritative source '%s' missing from context_files" % (tid, s, src))
    if c.get("seams") and c.get("negative_tests"):
        if len(c.get("negative_tests", [])) < len(c["seams"]):
            errs.append("%s: card declares %d seams but only %d negative_tests (at least one per declared seam required)" % (
                tid, len(c["seams"]), len(c.get("negative_tests", []))
            ))
    return c, errs


def input_hash(card):
    h = hashlib.sha256(card["_text"].encode("utf-8", "replace"))
    for f in sorted(card["context_files"]):
        fp = ROOT / f
        if fp.exists():
            h.update(fp.read_bytes())
    return h.hexdigest()


# ----------------------------------------------------------------------------- commands (run + confirm)
def run_cmd(cmd, cfg):
    t = time.time()
    try:
        r = subprocess.run(cmd, shell=True, cwd=str(ROOT), capture_output=True, timeout=cfg["command_timeout_seconds"])
        raw, code, to = (r.stdout or b"") + (r.stderr or b""), r.returncode, False
    except subprocess.TimeoutExpired as e:
        raw, code, to = (e.stdout or b"") + (e.stderr or b""), 124, True
    return code, raw.decode("utf-8", "replace"), round(time.time() - t, 1), to


def tail(text, n=40):
    lines = text.splitlines()
    return "\n".join(lines[-n:])


LOG_WRITE_ATTEMPTS = 64


def new_run_id():
    """Return a fresh identifier for one executed command (unique, not clock based)."""
    return uuid.uuid4().hex


def _log_component(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", str(value)).strip("_-")
    return cleaned or fallback


def write_command_log(label, text, run_id=None, seq_hint=0):
    """Store one command's output in a new, exclusive-created log file.

    The bytes written are exactly ``text`` encoded as UTF-8, so the digest of
    the saved file equals the digest recorded for that command. An existing log
    is never reopened for writing: a taken candidate identity is retried with a
    bounded fresh suffix, and exhausting the attempts fails loudly instead of
    destroying earlier evidence. The returned run_id is the effective identity
    of the log that was actually created, so two successful writes never report
    the same run identity.

    Returns (run_id, log_name, output_sha).
    """
    d = ai("logs")
    d.mkdir(parents=True, exist_ok=True)
    base_rid = _log_component(run_id or new_run_id(), "run")
    safe = _log_component(label, "log")
    data = text.encode("utf-8", "replace")
    seq = seq_hint if isinstance(seq_hint, int) and seq_hint > 0 else 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for attempt in range(LOG_WRITE_ATTEMPTS):
        # A collision means this candidate identity is already in use. Allocate a
        # fresh effective identity for the retry so the returned run_id always
        # names exactly one retained log.
        rid = base_rid if attempt == 0 else "%s-%d" % (base_rid, attempt)
        name = "%s-%04d-%s-%s.log" % (stamp, seq, safe, rid)
        target = d / name
        try:
            with target.open("xb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
        except FileExistsError:
            continue
        return rid, name, hashlib.sha256(data).hexdigest()
    raise OSError(
        "could not allocate an exclusive log for label %r after %d attempts; "
        "existing logs were left untouched" % (label, LOG_WRITE_ATTEMPTS)
    )


def save_log(led_seq_hint, label, text):
    """Backwards-compatible wrapper: save command output, return the log name."""
    return write_command_log(label, text, seq_hint=led_seq_hint)[1]


def run_recorded(cmd, cfg, label):
    code, text, secs, to = run_cmd(cmd, cfg)
    zero_tests = bool(NO_TESTS.search(text))
    suspect = zero_tests
    run_id, log, output_sha = write_command_log(label, text)
    if not JSON_MODE:
        print("\n$ %s\n%s\n[exit %s%s | %ss | run %s | log .ai/logs/%s]" % (cmd, tail(text), code, " TIMEOUT" if to else "", secs, run_id, log))
        if zero_tests:
            print("SUSPECT: weak verify command: exit %s and output says no tests ran. Treated as FAILURE." % code)
    return {
        "cmd": cmd, "exit": code, "timeout": to, "suspect": suspect, "secs": secs,
        "run_id": run_id, "output_sha": output_sha, "tail": tail(text, 15)[-1500:], "log": log,
        "ok": code == 0 and not suspect,
    }


def result_record(res):
    """Ledger-safe copy of one command result: keeps run identity, drops the echo tail."""
    return {k: v for k, v in res.items() if k != "tail"}


def confirmed(cfg, led, name):
    """True only when the current exact config command has a successful confirmation.

    The ledger decides: ``verified: true`` in config is not confirmation by itself.
    Records are read newest-first, so a later failed reconfirmation revokes an
    earlier success for the same name and command. Editing the configured command
    changes the exact text, which invalidates older confirmation records until the
    new command is confirmed itself.
    """
    if led is None:
        led = Ledger()
    entry = (cfg.get("commands", {}) or {}).get(name)
    if not entry or not entry.get("verified"):
        return False
    current = normalize_command(entry.get("cmd"))
    if not current:
        return False
    for e in reversed(led.entries()):
        if e.get("type") != "cmd_confirm":
            continue
        data = e.get("data") or {}
        if data.get("name") != name:
            continue
        if normalize_command(data.get("cmd")) != current:
            continue
        return bool(data.get("ok"))
    return False


# ----------------------------------------------------------------------------- reference checks
def pkg_deps(start_dir):
    d = start_dir
    while True:
        pj = d / "package.json"
        if pj.exists():
            try:
                j = json.loads(pj.read_text(encoding="utf-8"))
            except Exception:
                return None
            out = set()
            for k in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                out |= set((j.get(k) or {}).keys())
            return out
        if d == ROOT or d.parent == d:
            return None
        d = d.parent


def js_resolves(base, spec):
    cands = []
    target = (base / spec).resolve()
    bases = [target]
    m = re.match(r"^(.*)\.(js|jsx|mjs|cjs)$", str(target))
    if m:
        bases += [Path(m.group(1) + e) for e in (".ts", ".tsx")]
    for b in bases:
        cands.append(b)
        for e in JS_EXTS + [".json"]:
            cands.append(Path(str(b) + e))
            cands.append(b / ("index" + e))
    return any(c.exists() for c in cands)


def declared_python_dep(top):
    norm = top.lower().replace("_", "-")
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile"):
        p = ROOT / name
        if p.exists():
            t = p.read_text(encoding="utf-8", errors="replace").lower().replace("_", "-")
            if re.search(r"(^|[^a-z0-9])%s([^a-z0-9]|$)" % re.escape(norm), t):
                return True
    return False


def py_resolves(top):
    names = getattr(sys, "stdlib_module_names", None)
    if names and top in names:
        return "ok"
    for base in (ROOT, ROOT / "src"):
        if (base / top).is_dir() or (base / (top + ".py")).exists():
            return "ok"
    try:
        if importlib.util.find_spec(top) is not None:
            return "ok"
    except (ImportError, ValueError, AttributeError):
        pass
    if declared_python_dep(top):
        return "declared"
    return "missing"


def check_refs(ch):
    unresolved, unchecked, syntax = [], [], []
    for p, s in sorted(ch.items()):
        if s == "D":
            continue
        full = ROOT / p
        ext = full.suffix.lower()
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if ext == ".py":
            try:
                tree = ast.parse(text, filename=p)
            except SyntaxError as e:
                syntax.append("%s:%s: %s" % (p, e.lineno, e.msg))
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        r = py_resolves(a.name.split(".")[0])
                        if r == "missing":
                            unresolved.append("%s:%d: import '%s' is not stdlib, not local, not installed, not declared" % (p, node.lineno, a.name))
                        elif r == "declared":
                            unchecked.append("%s: '%s' declared but not installed in this interpreter" % (p, a.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:
                        base = full.parent
                        for _ in range(node.level - 1):
                            base = base.parent
                        if node.module:
                            t = base / node.module.replace(".", "/")
                            if not (t.is_dir() or Path(str(t) + ".py").exists()):
                                unresolved.append("%s:%d: relative import '.%s' not found" % (p, node.lineno, node.module))
                    elif node.module:
                        r = py_resolves(node.module.split(".")[0])
                        if r == "missing":
                            unresolved.append("%s:%d: import '%s' is not stdlib, not local, not installed, not declared" % (p, node.lineno, node.module))
                        elif r == "declared":
                            unchecked.append("%s: '%s' declared but not installed in this interpreter" % (p, node.module))
        elif ext in JS_EXTS:
            deps = pkg_deps(full.parent)
            ts_alias = any(
                (ROOT / f).exists() and re.search(r'"(paths|baseUrl)"', (ROOT / f).read_text(encoding="utf-8", errors="replace"))
                for f in ("tsconfig.json", "jsconfig.json")
            )
            for m in re.finditer(r"""(?:from|import|require\(|import\()\s*['"]([^'"\n]+)['"]""", text):
                spec = m.group(1)
                line = text.count("\n", 0, m.start()) + 1
                if spec.startswith("."):
                    if not js_resolves(full.parent, spec):
                        unresolved.append("%s:%d: relative import '%s' does not resolve to a file" % (p, line, spec))
                    continue
                if spec.startswith(("node:", "@/", "~", "#")) or spec.split("/")[0] in NODE_BUILTINS:
                    continue
                pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if deps is None or ts_alias:
                    unchecked.append("%s: '%s' (no package.json or path aliases in use)" % (p, spec))
                elif pkg not in deps:
                    unresolved.append("%s:%d: package '%s' is not declared in package.json" % (p, line, pkg))
        elif ext == ".json":
            try:
                json.loads(text)
            except ValueError as e:
                syntax.append("%s: invalid JSON (%s)" % (p, e))
        elif ext in CODE_EXTS:
            unchecked.append("%s: no built-in checker for %s; rely on a confirmed compiler/typecheck command" % (p, ext))
    return {"unresolved": unresolved, "unchecked": sorted(set(unchecked)), "syntax": syntax}


# ----------------------------------------------------------------------------- check (scope + scan + refs)
def run_check(cfg, st, tid, card, snap, cur):
    ch = diff_tree(snap, cur)
    fp = fingerprint(ch, cur)
    viol, flags = [], []
    for p, s in sorted(ch.items()):
        if not matches(p, card["allowed_files"]) or matches(p, card["forbidden_files"]):
            viol.append("%s %s is outside allowed_files" % (s, p))
        old, new = snap.get(p, {}), cur.get(p, {})
        if s == "D":
            flags.append(("deleted:%s" % p, "file deleted"))
            if old.get("test"):
                flags.append(("tests-weakened:%s:deleted" % p, "test file deleted"))
            continue
        if new.get("ph", 0) > old.get("ph", 0):
            flags.append(("placeholder:%s:+%d" % (p, new["ph"] - old.get("ph", 0)), "placeholder/stub/truncation marker added"))
        if old.get("lines") and new.get("lines") is not None and new["lines"] < old["lines"] * 0.6 and old["lines"] - new["lines"] >= 30:
            flags.append(("shrink:%s:%d->%d" % (p, old["lines"], new["lines"]), "file shrank sharply (possible truncation)"))
        if new.get("secrets", 0) > old.get("secrets", 0):
            flags.append(("secret:%s" % p, "possible secret/credential added"))
        if new.get("test") and s == "M":
            if new.get("asserts", 0) < old.get("asserts", 0):
                flags.append(("tests-weakened:%s:%d->%d" % (p, old.get("asserts", 0), new.get("asserts", 0)), "assertion count decreased"))
            if new.get("skips", 0) > old.get("skips", 0):
                flags.append(("skips-added:%s" % p, "skip/only/xfail marker added"))
        if s != "D" and (new.get("test") or TEST_PATH.search(p)):
            file_p = ROOT / p
            if file_p.is_file():
                txt = file_p.read_text(encoding="utf-8", errors="replace")
                if p.endswith(".py"):
                    for lno, msg in scan_tautological_python(p, txt):
                        flags.append(("tautological-assertion:%s:%d" % (p, lno), msg))
                elif any(p.endswith(ext) for ext in JS_EXTS):
                    for lno, msg in scan_tautological_js(p, txt):
                        flags.append(("tautological-assertion:%s:%d" % (p, lno), msg))

    # Heuristic gate: unanchored-mock on cards declaring seams
    if card.get("seams"):
        registered_fixtures = set()
        for f in card.get("fixtures", []):
            registered_fixtures.add(Path(f).name)
            registered_fixtures.add(Path(f).as_posix())
        mock_pat = re.compile(r"(jest\.mock|vi\.mock|msw|nock|unittest\.mock|@patch|patch\(|patch\.object|responses\.|Mock\(|MagicMock\()", re.I)
        for p, s in sorted(ch.items()):
            if s != "D" and cur.get(p, {}).get("test"):
                test_fp = ROOT / p
                if test_fp.is_file():
                    content = test_fp.read_text(encoding="utf-8", errors="replace")
                    if mock_pat.search(content):
                        anchored = False
                        for fix in registered_fixtures:
                            if fix and fix in content:
                                anchored = True
                                break
                        if not anchored:
                            flags.append(("unanchored-mock:%s" % p, "test uses mock constructs on seam card without loading registered fixture (heuristic: flags common mock libraries)"))

    waived = {w["flag"] for w in st["waivers"] if w["task"] == tid}
    is_waived = lambda f: f in waived or f.split(":")[0] in waived
    checker_errors = []
    for c in cfg.get("checkers", []):
        c_name = c.get("name", "checker")
        c_cmd = c.get("cmd")
        if not c_cmd:
            continue
        try:
            res = subprocess.run(
                c_cmd, shell=True, capture_output=True, text=True,
                cwd=str(ROOT), timeout=c.get("timeout", cfg.get("command_timeout_seconds", 60))
            )
            out_text = (res.stdout or "") + (res.stderr or "")
            parsed_json = None
            try:
                stripped = (res.stdout or "").strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    parsed_json = json.loads(stripped)
            except Exception:
                pass

            c_ok = (res.returncode == 0)
            if parsed_json and isinstance(parsed_json, dict):
                if parsed_json.get("ok") is False or parsed_json.get("status") in ("fail", "error"):
                    c_ok = False
                for fl in parsed_json.get("flags", []):
                    flags.append((fl, "pluggable checker '%s' flag" % c_name))
                for err in parsed_json.get("errors", []):
                    checker_errors.append("%s: %s" % (c_name, err))

            if not c_ok:
                if not any(f[0].startswith(c_name) or (parsed_json and f[0] in parsed_json.get("flags", [])) for f in flags):
                    flags.append(("checker-failed:%s" % c_name, "pluggable checker '%s' failed with exit code %s" % (c_name, res.returncode)))
                if out_text and not checker_errors:
                    checker_errors.append("%s: %s" % (c_name, out_text.strip()[:200]))
        except Exception as ex:
            flags.append(("checker-error:%s" % c_name, str(ex)))
            checker_errors.append("%s: exception %s" % (c_name, ex))

    unwaived = [(f, m) for f, m in flags if not is_waived(f)]
    refs = check_refs(ch)
    ok = not viol and not unwaived and not refs["unresolved"] and not refs["syntax"] and not checker_errors
    return {
        "ok": ok, "fp": fp, "changed": ch, "violations": viol, "flags": [f for f, _ in flags],
        "unwaived": unwaived, "waived": sorted(f for f, _ in flags if is_waived(f)), "refs": refs,
        "checker_errors": checker_errors,
    }


def print_check(r):
    print("Changed files: %d" % len(r["changed"]))
    for p, s in sorted(r["changed"].items()):
        print("  %s %s" % (s, p))
    for v in r["violations"]:
        print("SCOPE VIOLATION: %s" % v)
    for f, m in r["unwaived"]:
        print("FLAG: %s  (%s)\n  waive only with a real reason: osr waive <task> --flag \"%s\" --reason \"...\"" % (f, m, f))
    for err in r.get("checker_errors", []):
        print("CHECKER ERROR: %s" % err)
    for u in r["refs"]["unresolved"]:
        print("UNRESOLVED REFERENCE: %s" % u)
    for u in r["refs"]["syntax"]:
        print("SYNTAX ERROR: %s" % u)
    if r["refs"]["unchecked"]:
        print("UNCHECKED (no mechanical check available):")
        for u in r["refs"]["unchecked"][:15]:
            print("  - %s" % u)
    print("CHECK: %s" % ("PASS" if r["ok"] else "FAIL"))


def load_snap(tid):
    p = snap_path(tid)
    if not p.exists():
        die("Task %s has no snapshot. Run: osr start %s --model <name>" % (tid, tid))
    return json.loads(p.read_text(encoding="utf-8"))


def require_active(st, tid):
    ts = task_state(st, tid)
    if ts["status"] != "in_progress":
        die("Task %s is '%s', not in_progress. Run: osr start %s --model <name>" % (tid, ts["status"], tid))
    return ts


def require_not_failed_out(cfg, ts, tid):
    if ts["requires"] and ts["triaged_attempt"] >= ts["attempts"]:
        die("Attempt %d was diagnosed (%s). Begin a new attempt first: osr start %s --model <name>" % (ts["attempts"], ts["requires"]["layer"], tid))
    if ts["failures"] >= cfg["max_inner_failures"]:
        die("%d failures in attempt %d. Blind retries are blocked.\nDiagnose first: osr triage %s --layer <%s> --evidence \"...\" --change \"...\""
            % (ts["failures"], ts["attempts"], tid, "|".join(LAYERS)))


# ----------------------------------------------------------------------------- review validation
def evidence_error(path, line, snippet):
    if ".." in Path(path).parts:
        return "evidence path '%s' escapes the project" % path
    fp = ROOT / path
    if not fp.is_file():
        return "evidence file '%s' does not exist" % path
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    if line < 1 or line > len(lines):
        return "evidence line %d is outside %s (%d lines)" % (line, path, len(lines))
    window = " ".join(lines[max(0, line - 4): line + 3])
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    if norm(snippet) not in norm(window):
        return "snippet not found within 3 lines of %s:%d (quote the real code)" % (path, line)
    return None


def validate_spec_review(text, task_reqs, plan):
    errs, reqs = [], {}
    for raw in text.splitlines():
        ln = raw.strip().lstrip("-* ").replace("**", "")
        m = re.match(r"^(R\d+):\s*(PASS|FAIL|UNVERIFIED)\b(.*)$", ln)
        if not m:
            continue
        r, status, rest = m.group(1), m.group(2), m.group(3).strip()
        if r in reqs:
            errs.append("%s appears more than once" % r)
            continue
        if r not in task_reqs:
            errs.append("%s is not a requirement of this task" % r)
            continue
        entry = {"status": status, "evidence": None}
        if status == "PASS":
            if plan and plan.get(r, {}).get("check") == "manual":
                errs.append("%s is Check: manual, so it cannot be PASS. Use UNVERIFIED and ask the human to sign off." % r)
            em = re.search(r'@\s*(\S+?):(\d+)\s+"(.+)"\s*$', rest)
            if not em:
                errs.append('%s: PASS needs evidence in the form  @ path/to/file.ext:LINE "exact code snippet"' % r)
            else:
                e = evidence_error(em.group(1), int(em.group(2)), em.group(3))
                if e:
                    errs.append("%s: %s" % (r, e))
                entry["evidence"] = "%s:%s" % (em.group(1), em.group(2))
        else:
            if len(re.sub(r"^[\s\-:]+", "", rest)) < 10:
                errs.append("%s: %s needs a reason (10+ chars)" % (r, status))
            entry["reason"] = rest[:200]
        reqs[r] = entry
    for r in task_reqs:
        if r not in reqs:
            errs.append("%s has no line. Every requirement needs a line: R#: PASS|FAIL|UNVERIFIED ..." % r)
    declared = re.search(r"^\s*VERDICT:\s*(PASS|FAIL)\b", text, re.M)
    derived = "FAIL" if any(v["status"] == "FAIL" for v in reqs.values()) else "PASS"
    if not declared:
        errs.append("missing final line  VERDICT: PASS|FAIL")
    elif declared.group(1) != derived:
        errs.append("VERDICT says %s but the requirement lines imply %s" % (declared.group(1), derived))
    return errs, reqs, derived


def validate_quality_review(text, card=None, plan=None):
    errs, items = [], {}
    for raw in text.splitlines():
        ln = raw.strip().lstrip("-* ").replace("**", "")
        m = re.match(r"^(C\d+)\b[^:]*:\s*(PASS|FAIL|NA)\b\s*[-:\u2013\u2014]?\s*(.*)$", ln)
        if not m:
            continue
        cid, status, note = m.group(1), m.group(2), m.group(3).strip()
        if cid not in QUALITY_CHECKS:
            continue
        if cid in items:
            errs.append("%s appears more than once" % cid)
            continue
        need = 10 if status == "NA" else 15
        if len(note) < need:
            errs.append("%s: add a note (%d+ chars) saying what you inspected or why it is N/A" % (cid, need))
        items[cid] = status
    for cid in QUALITY_CHECKS:
        if cid not in items:
            errs.append("%s missing. Format: %s: PASS|FAIL|NA - what you inspected" % (cid, cid))
    brk, on = [], False
    for raw in text.splitlines():
        if re.match(r"^\s*BREAK_ATTEMPTS\b", raw):
            on = True
            continue
        if on:
            if re.match(r"^\s*VERDICT\b", raw):
                break
            m = re.match(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$", raw)
            if m and len(m.group(1).strip()) >= 25:
                brk.append(m.group(1).strip())
    if len(brk) < 3:
        errs.append("BREAK_ATTEMPTS needs 3+ concrete ways this code could fail, each 25+ chars ('- ' bullets)")

    # Seams section and citation validation
    declared_seams = card.get("seams", []) if card else []
    if declared_seams:
        plan_seams = getattr(plan, "seams", {}) if plan else {}
        cited_seams = {s: [] for s in declared_seams}
        for raw in text.splitlines():
            m = re.search(r'(?:SEAM\s+)?([a-zA-Z0-9_-]+)\s*:.*?@\s*(\S+?):(\d+)\s+"(.+?)"', raw)
            if m:
                sid, path, line_no, snippet = m.group(1), m.group(2), int(m.group(3)), m.group(4)
                if sid in declared_seams:
                    expected_source = plan_seams.get(sid, {}).get("source", "").strip()
                    if Path(path).as_posix() != Path(expected_source).as_posix():
                        errs.append("seam '%s': citation points to '%s', but authoritative source is '%s' (citations must point into the upstream source, not consumer files)" % (sid, path, expected_source))
                    else:
                        e = evidence_error(path, line_no, snippet)
                        if e:
                            errs.append("seam '%s': %s" % (sid, e))
                        else:
                            cited_seams[sid].append((path, line_no, snippet))
        for s in declared_seams:
            if not cited_seams.get(s):
                expected = plan_seams.get(s, {}).get("source", "").strip()
                errs.append("seam '%s' has no citations pointing into its authoritative source '%s' (format: SEAM %s: @ <source>:<line> \"snippet\")" % (s, expected, s))

    # Realtime Appendix validation if card kind is realtime
    card_kind = ""
    if card:
        k_val = card.get("kind")
        if isinstance(k_val, list):
            card_kind = k_val[0] if k_val else ""
        elif isinstance(k_val, str):
            card_kind = k_val
    if card_kind.lower() == "realtime":
        if not re.search(r"^##\s+Realtime Appendix\b", text, re.M | re.I):
            errs.append("Realtime Appendix ('## Realtime Appendix') is required for kind: realtime")
        else:
            dims = [
                ("teardown", r"[-*]\s*teardown\s*:\s*(.+)$"),
                ("backpressure", r"[-*]\s*backpressure\s*:\s*(.+)$"),
                ("race windows", r"[-*]\s*race\s*windows?\s*:\s*(.+)$"),
                ("time drift", r"[-*]\s*time\s*drift\s*:\s*(.+)$"),
            ]
            for dname, dpat in dims:
                m = re.search(dpat, text, re.M | re.I)
                if not m or len(m.group(1).strip()) < 15:
                    errs.append("Realtime Appendix: '%s' item missing or too short (15+ chars required describing %s behavior)" % (dname, dname))

    declared = re.search(r"^\s*VERDICT:\s*(PASS|FAIL)\b", text, re.M)
    derived = "FAIL" if any(v == "FAIL" for v in items.values()) else "PASS"
    if not declared:
        errs.append("missing final line  VERDICT: PASS|FAIL")
    elif declared.group(1) != derived:
        errs.append("VERDICT says %s but the checklist implies %s" % (declared.group(1), derived))
    return errs, items, derived


def _parameter_suffix(test_id):
    """Split one identity into ``(hierarchy, parameter_suffix)``.

    The parameter bracket content is kept verbatim; only the test hierarchy is
    available to the caller for ``::``/``.`` splitting.
    """
    s = str(test_id)
    i = s.find("[")
    if i != -1 and s.rstrip().endswith("]"):
        return s[:i], s[i:]
    return s, ""


def terminal_test_name(test_id):
    """Terminal name of one canonical test identity (parameters preserved).

    Only the test hierarchy is split on ``::`` and ``.``. Parameter content is
    kept exactly as printed, so ``tests/test_p.py::test_add[value.with.dot]``
    keeps ``test_add[value.with.dot]`` instead of collapsing to ``dot]``.
    """
    hierarchy, parameter = _parameter_suffix(test_id)
    tail = hierarchy.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    return tail + parameter


def _qualified_identity(test_id):
    """True when a declaration carries a path, module or class hierarchy."""
    hierarchy, _ = _parameter_suffix(test_id)
    return "." in hierarchy or "::" in hierarchy


def _canonical_from_unittest(name, parenthetical):
    """Canonical identity for one verbose unittest line.

    ``method (module.Class.method) ... ok`` already carries the full identity.
    ``method (module.Class) ... ok`` (the captured vendor fixture shape) only
    carries the class, so the printed method is appended exactly once.
    """
    if not parenthetical or parenthetical == name:
        return name
    if parenthetical.endswith("." + name):
        return parenthetical
    return parenthetical + "." + name


def extract_test_identities(text):
    """Return ``(canonical, aliases)`` identities from one run's supplied output.

    Canonical identities are the tests the runner actually executed: a printed
    qualified id or a printed bare name. Aliases are short terminal names
    derived for convenient declarations. They are never treated as separately
    executed tests and never authorise a different test.

    Only ``text`` is evidence: report files in ``.ai/logs`` are never scanned,
    so an old XML or log file cannot stand in for this run. Supported runner
    shapes are unittest verbose ``method (module.Class.method) ... ok``,
    ``method (module.Class) ... ok``, bare ``name ... ok`` lines, pytest node
    ids (``file::Class::test[param]``) and the tick form.
    """
    canonical, aliases = set(), set()

    def add(canonical_id, alias=None):
        canonical_id = (canonical_id or "").strip()
        if not canonical_id:
            return
        canonical.add(canonical_id)
        alias_id = (alias or terminal_test_name(canonical_id)).strip()
        if alias_id and alias_id != canonical_id:
            aliases.add(alias_id)

    for m in re.finditer(r"^([A-Za-z0-9_.:/\[\]-]+)(?:\s+\(([^)]+)\))?\s+\.\.\.\s+ok\b", text, re.M):
        name, parenthetical = m.group(1), (m.group(2) or "").strip()
        add(_canonical_from_unittest(name, parenthetical), name)
    for m in re.finditer(r"^(\S+::\S+)\s+PASSED\b", text, re.M):
        add(m.group(1))
    for m in re.finditer(r"^(?:PASSED\s+)(\S+::\S+)\s*$", text, re.M):
        add(m.group(1))
    for m in re.finditer(r"^[ \t]*(?:✓|√)\s+(\S+)", text, re.M):
        add(m.group(1))
    return sorted(canonical), sorted(aliases - canonical)


def extract_passed_tests(text):
    """All current-run identities: canonical evidence plus compatibility aliases.

    This flat list stays the serialisable evidence form. Resolution still uses
    the canonical half from ``extract_test_identities`` so an alias can never
    stand in for a test that did not run.
    """
    canonical, aliases = extract_test_identities(text)
    return sorted(set(canonical) | set(aliases))


def resolve_test_declaration(declared, canonical_ids):
    """Resolve one declared test name against this run's canonical identities.

    ``canonical_ids`` is the set of identities the runner actually executed, so
    a derived short alias can never masquerade as a separate test. Returns
    ``(matched_ids, reason)`` where reason is ``ok``, ``missing``, ``ambiguous``
    or ``invalid``. A qualified declaration matches only the identical
    canonical identity. A short declaration matches only when exactly one
    canonical identity has that terminal name; several matches are ambiguous
    and no match is missing. A bare canonical identity that happens to equal
    the declaration is counted with the qualified identities, so it cannot
    hide a same-name collision. Parameter brackets are compared verbatim.
    There is no substring, suffix or prefix matching.
    """
    declared = (declared or "").strip()
    if (not declared or re.search(r"[\s*?<>]", declared)
            or declared.count("[") != declared.count("]")):
        return [], "invalid"
    canonical = set(canonical_ids or ())
    if _qualified_identity(declared):
        return ([declared], "ok") if declared in canonical else ([], "missing")
    matches = sorted(i for i in canonical if terminal_test_name(i) == declared)
    if len(matches) == 1:
        return matches, "ok"
    if not matches:
        return [], "missing"
    return matches, "ambiguous"


def named_test_message(declared, reason, matches, negative=False):
    """Actionable diagnostic for a declaration that did not resolve to a pass."""
    kind = "named negative test" if negative else "test"
    if reason == "ambiguous":
        return "%s '%s' is ambiguous: current run output matches %s; declare a qualified name" % (
            kind, declared, ", ".join(matches)
        )
    if reason == "invalid":
        return "%s '%s' is empty or unsupported; declare a concrete test name" % (kind, declared)
    return "%s '%s' did not run and pass in the current run output" % (kind, declared)


def acceptance_test_tags(ac_text):
    """Declared test identities inside one acceptance line's ``[...]`` tags.

    The scan follows bracket depth and keeps the whole content of every
    outermost declaration, so paths, ``::`` node separators, whitespace and
    nested parameter brackets stay part of one identity instead of being
    skipped or reduced to an inner parameter. ``acceptance_test_tags(
    "Use [tests/test_p.py::test_add[[nested]]]")`` therefore returns
    ``["tests/test_p.py::test_add[[nested]]"]``, never ``["nested"]``, and a
    declaration such as ``[tests/test_p.py::test_add[value with space]]`` is
    returned whole for validation to reject as unsupported. An unterminated
    declaration is returned as its remaining text so validation can reject it;
    every returned tag becomes a gate and none is silently dropped.
    """
    text = ac_text or ""
    tags = []
    depth = 0
    start = -1
    for index, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = index + 1
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                tags.append(text[start:index])
                start = -1
    if depth and start >= 0:
        tags.append(text[start:])
    return tags


# ----------------------------------------------------------------------------- gates and next action
def gate_status(cfg, st, led, tid, card, cur=None, snap=None):
    ts = task_state(st, tid)
    a = ts["attempts"]
    if cur is None:
        cur = walk_tree(cfg)
    if snap is None:
        snap = load_snap(tid)
    ch = diff_tree(snap, cur)
    fp = fingerprint(ch, cur)
    start_entry = led.latest("start", tid, a)
    start_seq = start_entry["seq"] if start_entry else None
    gates = []

    def fresh(e):
        return (e is not None and e["data"].get("fp") == fp
                and e["data"].get("start_seq") == start_seq)

    e = led.latest("verify", tid, a)
    gates.append(("verify", bool(e and e["data"].get("ok") and fresh(e)),
                  "no passing verify for the current code" if not e or not fresh(e) or not e["data"].get("ok") else "ok"))
    for stage in ("spec", "quality"):
        e_rev = led.latest("review", tid, a, stage)
        good = bool(e_rev and e_rev["data"].get("verdict") == "PASS" and fresh(e_rev))
        gates.append(("review-" + stage, good, "no passing, current %s review" % stage if not good else "ok"))

    plan, _ = parse_plan()
    if plan and e and fresh(e):
        passed_tests = set(e["data"].get("passed_tests", []))
        canonical_tests = e["data"].get("canonical_tests")
        evidence = set(canonical_tests) if canonical_tests is not None else passed_tests
        for r_id in card.get("requirements", []):
            req = plan.get(r_id, {})
            for ac in req.get("ac", []):
                for test_id in acceptance_test_tags(ac):
                    matched, reason = resolve_test_declaration(test_id, evidence)
                    test_passed = reason == "ok"
                    gates.append((
                        "test-" + test_id,
                        test_passed,
                        "ok" if test_passed else named_test_message(test_id, reason, matched)
                    ))
        for neg in card.get("negative_tests", []):
            matched, reason = resolve_test_declaration(neg, evidence)
            neg_passed = reason == "ok"
            gates.append((
                "negative-test-" + neg,
                neg_passed,
                "ok" if neg_passed else named_test_message(neg, reason, matched, negative=True)
            ))
    return gates, fp


def next_action():
    root_ai = ai()
    if not root_ai.exists():
        return "osr init"
    cfg, st, led = ctx()
    if not any(confirmed(cfg, led, n) for n in cfg["commands"]) and not cfg["allow_no_commands"]:
        if not cfg["commands"]:
            return "osr detect   (then review .ai/config.json, then: osr confirm-commands)"
        return "osr confirm-commands   (no command is confirmed yet; fix .ai/config.json if a command is wrong)"
    plan, perrs = parse_plan()
    if perrs:
        return "Fix PLAN.md:\n  - " + "\n  - ".join(perrs)
    p = ai("PLAN.md").read_text(encoding="utf-8")
    if st["plan_hash"] != sha_text(p):
        return "STOP: ask the human to review PLAN.md. Only the human approves it: osr approve-plan --by <name>"
    if st.get("config_hash") and st["config_hash"] != sha_config():
        return "STOP: config.json changed since plan approval. The human must re-run approve-plan: osr approve-plan --by <name>"
    ids = task_ids()
    if not ids:
        return "Write task cards in .ai/tasks/ (see assets/task-card.md) until every requirement is covered, then: osr task-check --all"
    covered = set()
    errs = []
    for t in ids:
        c, e = validate_card(t, cfg, plan)
        errs += e
        if c:
            covered |= set(c["requirements"])
    if errs:
        return "Fix task cards:\n  - " + "\n  - ".join(errs[:12])
    unc = [r for r in plan if r not in covered]
    if unc:
        return "Requirements not covered by any task: %s. Add task cards." % ", ".join(unc)
    blocked = []
    for t in ids:
        ts = task_state(st, t)
        if ts["status"] == "done":
            continue
        if ts["blocked"]:
            blocked.append("%s: %s" % (t, ts["blocked"]))
            continue
        c = parse_card(t)
        if any(task_state(st, d)["status"] != "done" for d in c["depends_on"]):
            continue
        if ts["status"] == "todo" or ts["attempts"] == 0:
            return "osr start %s --model <your-model-name>" % t
        if ts["requires"] and ts["triaged_attempt"] >= ts["attempts"]:
            return "osr start %s --model <your-model-name>   (new attempt; triage layer '%s' requires a changed input)" % (t, ts["requires"]["layer"])
        if ts["failures"] >= cfg["max_inner_failures"]:
            return "osr triage %s --layer <%s> --evidence \"...\" --change \"...\"" % (t, "|".join(LAYERS))
        gates, _ = gate_status(cfg, st, led, t, c)
        for name, ok, msg in gates:
            if not ok:
                if name == "verify":
                    return "Implement/fix %s within allowed_files, then: osr verify %s" % (t, t)
                stage = name.split("-")[1]
                return "Write .ai/reviews/%s.%s.md (template assets/%s-review.md), then: osr review %s %s --reviewer <name>" % (t, stage, stage, t, stage)
        return "osr done %s" % t
    if blocked:
        return "BLOCKED, human needed:\n  - " + "\n  - ".join(blocked) + "\n  (human runs: osr unblock <task> --by <name> --note \"...\")"
    return "osr audit"


# ----------------------------------------------------------------------------- command handlers
def cmd_init(a):
    for d in ("tasks", "reviews", "logs", "snapshots"):
        ai(d).mkdir(parents=True, exist_ok=True)
    first = not ai("config.json").exists()
    if first:
        save_cfg(DEFAULT_CFG)
    if not ai("PLAN.md").exists():
        src = ASSETS / "PLAN.md"
        ai("PLAN.md").write_text(src.read_text(encoding="utf-8") if src.exists() else "# Plan\n\n## Goal\n\n## Non-goals\n\n## Requirements\n", encoding="utf-8")
    if not ai("state.json").exists():
        save_state(load_state())
    ai(".gitignore").write_text("logs/\nsnapshots/\n", encoding="utf-8")
    led = Ledger()
    if not led.entries():
        led.append("init", version=VERSION)
    print("Initialized .ai/  (commit PLAN.md, tasks/, reviews/, ledger.jsonl, config.json, state.json)")
    print("NEXT: %s" % next_action())


def detect_commands():
    c = {}

    def has(*n):
        return any((ROOT / x).exists() for x in n)

    def add(lang, name, cmd):
        key = name if name not in c else "%s-%s" % (lang, name)
        c[key] = cmd

    if has("package.json"):
        try:
            sc = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
        except Exception:
            sc = {}
        pm = "pnpm" if has("pnpm-lock.yaml") else "yarn" if has("yarn.lock") else "bun" if has("bun.lockb", "bun.lock") else "npm"
        for n in ("test", "lint", "build", "typecheck"):
            if n in sc:
                add("node", n, pm + (" test" if n == "test" else " run " + n))
        if "typecheck" not in sc and has("tsconfig.json"):
            add("node", "typecheck", "npx tsc --noEmit")
    if has("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "pytest.ini", "tox.ini", "Pipfile"):
        add("py", "test", "python -m pytest -q")
        blob = " ".join((ROOT / f).read_text(encoding="utf-8", errors="replace") for f in ("pyproject.toml", "setup.cfg", "tox.ini") if (ROOT / f).exists())
        if has("ruff.toml", ".ruff.toml") or "ruff" in blob:
            add("py", "lint", "ruff check .")
        if has("mypy.ini") or "mypy" in blob:
            add("py", "typecheck", "mypy .")
    if has("go.mod"):
        add("go", "build", "go build ./...")
        add("go", "lint", "go vet ./...")
        add("go", "test", "go test ./...")
    if has("Cargo.toml"):
        add("rust", "build", "cargo check")
        add("rust", "test", "cargo test")
    if has("pom.xml"):
        add("java", "test", "mvn -q test")
    if has("build.gradle", "build.gradle.kts"):
        add("java", "test", "gradlew test" if os.name == "nt" else "./gradlew test")
    if any(ROOT.glob("*.sln")) or any(ROOT.glob("*.csproj")):
        add("dotnet", "build", "dotnet build")
        add("dotnet", "test", "dotnet test")
    if has("composer.json"):
        add("php", "test", "composer test")
    if has("Gemfile"):
        add("ruby", "test", "bundle exec rspec" if (ROOT / "spec").exists() else "bundle exec rake test")
    if has("mix.exs"):
        add("elixir", "test", "mix test")
    if has("pubspec.yaml"):
        add("dart", "test", "dart test")
    if has("Package.swift"):
        add("swift", "build", "swift build")
        add("swift", "test", "swift test")
    if has("Makefile") and re.search(r"^test\s*:", (ROOT / "Makefile").read_text(encoding="utf-8", errors="replace"), re.M):
        add("make", "test", "make test")
    return c


def cmd_detect(a):
    cfg, st, led = ctx()
    found = detect_commands()
    for n, cmd in found.items():
        if n not in cfg["commands"]:
            cfg["commands"][n] = {"cmd": cmd, "verified": False}
    if not cfg["global_verify"]:
        cfg["global_verify"] = list(cfg["commands"])
    save_cfg(cfg)
    print("Detected candidate commands (UNVERIFIED, these are guesses from marker files):")
    for n, c in cfg["commands"].items():
        print("  %-12s %s  verified=%s" % (n, c["cmd"], c["verified"]))
    if not found:
        print("  none found. Add commands by hand in .ai/config.json (\"commands\": {\"test\": {\"cmd\": \"...\", \"verified\": false}}),")
        print("  or set \"allow_no_commands\": true for a brand-new project (every requirement then needs human sign-off).")
    print("Review .ai/config.json (remove wrong commands, edit global_verify), then run: osr confirm-commands")


def cmd_confirm(a):
    cfg, st, led = ctx()
    if not cfg["commands"]:
        die("No commands configured. Run: osr detect")
    for n, c in cfg["commands"].items():
        r = run_recorded(c["cmd"], cfg, "confirm-" + n)
        c["verified"] = r["ok"]
        led.append("cmd_confirm", name=n, cmd=c["cmd"], ok=r["ok"], exit=r["exit"], run_id=r["run_id"], log=r["log"], output_sha=r["output_sha"])
        print("=> %s: %s" % (n, "CONFIRMED" if r["ok"] else "NOT CONFIRMED (fix the command or the project, or remove it from config.json)"))
    save_cfg(cfg)
    print("NEXT: %s" % next_action())


def cmd_env_check(a):
    cfg, st, led = ctx()
    names = [n for n in cfg["env_smoke"] if n in cfg["commands"]] or list(cfg["commands"])
    ok = True
    for n in names:
        r = run_recorded(cfg["commands"][n]["cmd"], cfg, "env-" + n)
        ok = ok and r["ok"]
    led.append("env_check", names=names, ok=ok)
    print("ENV CHECK: %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


def cmd_plan_check(a):
    plan, errs = parse_plan()
    warnings = []
    if plan:
        seams = getattr(plan, "seams", {})
        if not seams:
            external_kw = re.compile(r"\b(api|service|endpoint|queue|socket|websocket|grpc|rpc|http|rest)\b", re.I)
            for r, v in plan.items():
                text_to_check = v["text"] + " " + " ".join(v.get("ac", []))
                m = external_kw.search(text_to_check)
                if m:
                    warnings.append("PLAN WARNING: (heuristic keyword match) requirement %s mentions external interface ('%s') but Seams table is empty (consider declaring in ## Seams)" % (r, m.group(1)))
    for w in warnings:
        print(w)
    for e in errs:
        print("PLAN ERROR: " + e)
    if not errs:
        print("PLAN OK: %d requirements (%d manual)" % (len(plan), sum(1 for v in plan.values() if v["check"] == "manual")))
    sys.exit(1 if errs else 0)


def cmd_approve(a):
    cfg, st, led = ctx()
    check_approval_secret(cfg, a)
    plan, errs = parse_plan()
    if errs:
        die("Plan invalid:\n  " + "\n  ".join(errs))
    if not any(confirmed(cfg, led, n) for n in cfg["commands"]) and not cfg["allow_no_commands"]:
        die("No confirmed verification command. Run detect + confirm-commands (or set allow_no_commands for a brand-new project).")
    active = [t for t, ts in (st.get("tasks") or {}).items() if ts.get("status") == "in_progress"]
    if active:
        die("Task(s) %s are in_progress. A new approval epoch cannot be established while work is active. "
            "Finish them, or the human must explicitly retire/reset them first; active work is never rebased silently." % ", ".join(sorted(active)))
    seams = getattr(plan, "seams", {})
    if seams:
        print("\n=== Declared Seams in PLAN.md ===")
        print("%-18s | %-16s | %-18s | %-30s | %s" % ("Seam ID", "Consumer", "Provider", "Authoritative Source", "How Checked"))
        print("-" * 105)
        for sid, sinfo in sorted(seams.items()):
            print("%-18s | %-16s | %-18s | %-30s | %s" % (
                sid, sinfo.get("consumer", ""), sinfo.get("provider", ""), sinfo.get("source", ""), sinfo.get("how", "")
            ))
        print("=" * 105 + "\n")
    by_val = join_arg(a.by)
    # Everything bound by the approval is computed and rechecked under the lock.
    # The unlocked state read above only fails fast; it never becomes the saved
    # state, so a task that becomes active while this call waits is preserved and
    # the approval is refused (no silent rebase, no lost task entry).
    with LedgerLock(timeout=0.3):
        current_st = load_state()
        active = [t for t, ts in (current_st.get("tasks") or {}).items() if ts.get("status") == "in_progress"]
        if active:
            die("Task(s) %s are in_progress. A new approval epoch cannot be established while work is active. "
                "Finish them, or the human must explicitly retire/reset them first; active work is never rebased silently." % ", ".join(sorted(active)))
        h = sha_text(ai("PLAN.md").read_text(encoding="utf-8"))
        cfg_h = sha_config()
        plan_raw = file_sha(ai("PLAN.md"))
        ignore = ignore_digest(cfg)
        baseline = manifest_from_tree(walk_tree(cfg))
        baseline_sha = manifest_digest(baseline)
        entries = led.entries()
        epoch = len(entries) + 1
        fresh = {
            "epoch": epoch,
            "plan_hash": h,
            "plan_raw_sha": plan_raw,
            "config_sha": cfg_h,
            "ignore_sha": ignore,
            "manifest": baseline,
            "manifest_sha": baseline_sha,
        }
        current_st["plan_hash"] = h
        current_st["config_hash"] = cfg_h
        current_st["freshness"] = fresh
        save_state(current_st)
        body = led.append(
            "plan_approved", by=by_val, plan_hash=h, config_hash=cfg_h,
            approval_epoch=epoch, plan_raw_sha=plan_raw, ignore_sha=ignore,
            manifest_sha=baseline_sha,
        )
        if body["seq"] != epoch:
            die("Approval ledger sequence changed while the lock was held; re-run approve-plan.", code=EXIT_INTEGRITY)
    print("Plan approved by %s. Any later edit to PLAN.md or config.json voids approval until re-approved." % by_val)
    print("Approval epoch %d binds %d governed files (baseline digest %s)." % (epoch, len(baseline), baseline_sha))


def cmd_task_check(a):
    cfg, st, led = ctx()
    plan, perrs = parse_plan()
    ids = task_ids() if a.all or not a.task else [a.task]
    allerrs = []
    for t in ids:
        c, e = validate_card(t, cfg, plan)
        allerrs += e
        print("%s: %s" % (t, "OK" if not e else "INVALID"))
        if c and c.get("seams") and c.get("fixtures") and not c.get("conformance"):
            print("  TASK WARNING: %s declares fixtures for seam(s) %s without 'conformance:' commands (audit will report UNVERIFIED)" % (t, ", ".join(c.get("seams", []))))
    for e in allerrs:
        print("  - " + e)
    if a.all and plan:
        covered = set()
        for t in ids:
            c = parse_card(t)
            covered |= set(c["requirements"])
        for r in plan:
            if r not in covered:
                print("  - requirement %s is not covered by any task" % r)
                allerrs.append(r)
    sys.exit(1 if allerrs else 0)


def cmd_start(a):
    cfg, st, led = ctx()
    tid = a.task
    plan, perrs = parse_plan()
    if perrs:
        die("Plan invalid; fix before starting:\n  " + "\n  ".join(perrs))
    ensure_plan_and_config_approved(st)
    card, errs = validate_card(tid, cfg, plan)
    if errs:
        die("Task card invalid:\n  " + "\n  ".join(errs))
    ts = task_state(st, tid)
    for other, ots in (st.get("tasks") or {}).items():
        if other != tid and ots.get("status") == "in_progress":
            die("Task %s is already in_progress. Only one active task is allowed; finish it before starting %s." % (other, tid))
    for d in card["depends_on"]:
        if task_state(st, d)["status"] != "done":
            die("Dependency %s is not done." % d)
    if ts["status"] == "done":
        die("Task %s is already done. (Plan changed? human runs: osr reset %s --by <name> --reason \"...\")" % (tid, tid))
    if ts["blocked"]:
        die("Task %s is blocked: %s\nHuman must run: osr unblock %s --by <name> --note \"...\"" % (tid, ts["blocked"], tid))
    ih = input_hash(card)
    if ts["attempts"] >= 1:
        if ts["triaged_attempt"] < ts["attempts"]:
            die("Attempt %d has no diagnosis. If it failed, run: osr triage %s --layer <%s> --evidence \"...\" --change \"...\"\nIf it is still going, continue it; do not restart." % (ts["attempts"], tid, "|".join(LAYERS)))
        if ts["attempts"] >= cfg["max_attempts"] + ts["extra_attempts"]:
            die("Attempt cap (%d) reached. Stop and ask the human; they may grant more: osr unblock %s --extra-attempts N --by <name> --note \"...\"" % (cfg["max_attempts"], tid))
        req = ts["requires"] or {}
        layer = req.get("layer")
        if layer in ("prompt", "context") and ih == req.get("input_hash"):
            die("Triage said '%s' fault, but the task card and context files are unchanged. A retry must change its input. Edit the card/context, then start again." % layer)
        if layer == "model" and (a.model in (None, "unknown", req.get("model"))):
            die("Triage said 'model' fault: start with a DIFFERENT model via --model (previous: %s)." % req.get("model"))
        if layer == "environment":
            e = led.latest("env_check")
            if not e or e["seq"] < req.get("seq", 0) or not e["data"].get("ok"):
                die("Triage said 'environment' fault: fix the environment, then run: osr env-check (must pass).")
    cur = walk_tree(cfg)
    freshness = evaluate_acceptance(cfg, st, led, plan, current_tree=cur)
    if freshness["failures"]:
        die("Pre-start drift: the governed tree does not match the last accepted artifact set:\n  - "
            + "\n  - ".join(freshness["failures"])
            + "\nDo not resnapshot it. A later task must be reviewed, or the human must re-approve the plan.")
    if freshness["legacy"]:
        start_base_sha = None
        print("WARNING: this approval epoch is legacy (no governed baseline). "
              "This task's completion will audit as UNVERIFIED; it cannot launder unreviewed bytes.")
    else:
        if not freshness["derivable"]:
            die("The last accepted artifact set cannot be derived from the current evidence. "
                "Repair the missing/failed completion evidence or ask the human to re-approve before starting.")
        start_base_sha = manifest_digest(freshness["accepted"])
    existing_snap = snapshot_map(tid)
    snap_map = manifest_from_tree(cur) if existing_snap is None else existing_snap
    start_snapshot_sha = manifest_digest(snap_map)
    if not freshness["legacy"] and start_snapshot_sha != start_base_sha:
        die("Task %s's start snapshot does not equal the accepted map at start; reset the task and start again." % tid)
    plan_raw = file_sha(ai("PLAN.md"))
    cfg_sha = sha_config()
    ignore_sha = ignore_digest(cfg)
    card_sha = file_sha(ai("tasks", tid + ".md"))
    baseline = {}
    for n in cfg.get("global_verify", []):
        if n in cfg.get("commands", {}) and confirmed(cfg, led, n):
            res = run_recorded(cfg["commands"][n]["cmd"], cfg, "%s-baseline-%s" % (tid, n))
            baseline[n] = {"ok": res["ok"], "exit": res["exit"], "sha": res["output_sha"], "run_id": res["run_id"], "log": res["log"]}
    for i, v in enumerate(card["verify"]):
        if not TRIVIAL_CMD.match(v) and is_verify_cmd_confirmed(v, cfg, led):
            res = run_recorded(v, cfg, "%s-baseline-task-%d" % (tid, i))
            baseline["task_%d" % i] = {"cmd": v, "ok": res["ok"], "exit": res["exit"], "sha": res["output_sha"], "run_id": res["run_id"], "log": res["log"]}

    with LedgerLock(timeout=0.3):
        current_st = load_state()
        for other, ots in (current_st.get("tasks") or {}).items():
            if other != tid and ots.get("status") == "in_progress":
                die("Task %s became in_progress while this start was waiting. Only one active task is allowed; finish it before starting %s." % (other, tid))
        current_ts = task_state(current_st, tid)
        if current_ts["status"] == "done":
            die("Task %s is already done. (Plan changed? human runs: osr reset %s --by <name> --reason \"...\")" % (tid, tid))
        # Revalidate this task's own lineage from current state. A concurrent start
        # of the same task must not be advanced to attempt 2 without triage.
        if (current_ts["status"] != ts["status"]
                or current_ts["attempts"] != ts["attempts"]
                or (current_ts.get("start") or {}).get("seq") != (ts.get("start") or {}).get("seq")):
            die("Task %s changed while this start was preparing (status %r -> %r, attempt %s -> %s). "
                "Refusing to advance a stale attempt; re-run osr start %s." % (
                    tid, ts["status"], current_ts["status"], ts["attempts"], current_ts["attempts"], tid))
        # Revalidate the approval/card/config binding used to prepare the start,
        # so a queued start cannot stamp an older epoch after a reapproval.
        approval = led.latest("plan_approved")
        adata = (approval or {}).get("data") or {}
        if approval is None or approval["seq"] != freshness["epoch"]:
            die("The approval epoch changed while this start was waiting. Re-run osr start %s under the current approval." % tid)
        if (file_sha(ai("tasks", tid + ".md")) != card_sha
                or file_sha(ai("PLAN.md")) != plan_raw
                or sha_config() != cfg_sha
                or ignore_digest(cfg) != ignore_sha):
            die("The task card, PLAN.md, config.json or the governed ignore policy changed while this start was waiting. "
                "Re-run osr start %s under the current approval." % tid)
        for key, bound in (("plan_raw_sha", plan_raw), ("ignore_sha", ignore_sha), ("config_hash", cfg_sha)):
            if adata.get(key) is not None and adata.get(key) != bound:
                die("The approval binding for %s changed while this start was waiting. Re-run osr start %s under the current approval." % (key, tid))
        attempt = current_ts["attempts"] + 1
        if not snap_path(tid).exists():
            snap_path(tid).write_text(json.dumps(cur), encoding="utf-8")
        start_record = {
            "approval_epoch": freshness["epoch"],
            "start_base_sha": start_base_sha,
            "start_snapshot_sha": start_snapshot_sha,
            "plan_raw_sha": plan_raw,
            "config_sha": cfg_sha,
            "ignore_sha": ignore_sha,
            "card_sha": card_sha,
        }
        current_ts.update({
            "status": "in_progress", "attempts": attempt, "failures": 0,
            "model": a.model or "unknown", "input_hash": ih, "requires": None,
            "baseline": baseline, "start": start_record,
        })
        save_state(current_st)
        body = led.append(
            "start", tid, attempt, model=current_ts["model"], input_hash=ih, baseline=baseline,
            **start_record
        )
        current_ts["start"]["seq"] = body["seq"]
        save_state(current_st)
        st.clear()
        st.update(current_st)
        ts = current_ts
    if JSON_MODE:
        emit_json({
            "ok": True,
            "exit_code": 0,
            "status": "ok",
            "task": tid,
            "attempt": ts["attempts"],
            "model": ts["model"],
            "allowed_files": card["allowed_files"]
        }, code=0)
    print("Task %s started (attempt %d). Allowed files: %s" % (tid, ts["attempts"], ", ".join(card["allowed_files"])))
    print("Read ONLY the card and its context_files. Implement, then run: osr verify %s" % tid)


def cmd_check(a):
    cfg, st, led = ctx()
    ts = require_active(st, a.task)
    card, errs = validate_card(a.task, cfg, parse_plan()[0])
    r = run_check(cfg, st, a.task, card, load_snap(a.task), walk_tree(cfg))
    print_check(r)
    led.append("check", a.task, ts["attempts"], ok=r["ok"], fp=r["fp"], flags=r["flags"], unchecked=r["refs"]["unchecked"][:30])
    sys.exit(0 if r["ok"] else 1)


def cmd_verify(a):
    cfg, st, led = ctx()
    ensure_plan_and_config_approved(st)
    tid = a.task
    ts = require_active(st, tid)
    require_not_failed_out(cfg, ts, tid)
    card, errs = validate_card(tid, cfg, parse_plan()[0])
    if errs:
        die("Task card invalid:\n  " + "\n  ".join(errs))

    # Fixture registration and hash integrity check
    for fix in card.get("fixtures", []):
        fix_fp = ROOT / fix
        try:
            norm_fix = fix_fp.relative_to(ROOT).as_posix() if fix_fp.is_file() else Path(fix).as_posix()
        except Exception:
            norm_fix = fix.replace("\\", "/")
        reg = st.get("fixtures", {}).get(norm_fix)
        if not reg:
            die("Fixture '%s' is not registered. Register it with: osr fixture-add %s --seam <id> --source \"...\"" % (fix, fix))
        if not fix_fp.is_file():
            die("Fixture file '%s' does not exist." % fix)
        cur_h = hashlib.sha256(fix_fp.read_bytes()).hexdigest()
        if cur_h != reg.get("sha256"):
            die("Fixture hash mismatch for '%s' (registered: %s, current: %s). Re-register with: osr fixture-add %s --seam %s --source \"...\"" % (
                fix, reg.get("sha256"), cur_h, fix, reg.get("seam", "seam_id")
            ))

    snap = load_snap(tid)
    start_entry = led.latest("start", tid, ts["attempts"])
    if not start_entry:
        die("No start record exists for %s attempt %d. Run: osr start %s --model <name>" % (tid, ts["attempts"], tid))
    start_seq = start_entry["seq"]
    cur_pre = walk_tree(cfg)
    r = run_check(cfg, st, tid, card, snap, cur_pre)
    if not JSON_MODE:
        print_check(r)
    led.append("check", tid, ts["attempts"], ok=r["ok"], fp=r["fp"], flags=r["flags"], unchecked=r["refs"]["unchecked"][:30])
    if not r["ok"]:
        ts["failures"] += 1
        save_state(st)
        led.append("verify", tid, ts["attempts"], ok=False, fp=r["fp"], start_seq=start_seq, reason="pre-check failed", results=[])
        if JSON_MODE:
            emit_json({
                "ok": False,
                "exit_code": 2,
                "status": "gate_failed",
                "task": tid,
                "reason": "static checks failed",
                "failures": ts["failures"],
                "max_failures": cfg["max_inner_failures"],
                "flags": r["flags"]
            }, code=2)
        print("VERIFY: FAIL (static checks failed; commands not run). Failures this attempt: %d/%d" % (ts["failures"], cfg["max_inner_failures"]))
        sys.exit(2)

    cmds = []
    for n in cfg["global_verify"]:
        if n not in cfg["commands"]:
            continue
        if not confirmed(cfg, led, n):
            die("Global command '%s' is not confirmed. Run: osr confirm-commands" % n)
        cmds.append((n, cfg["commands"][n]["cmd"]))
    for v in card["verify"]:
        if not is_verify_cmd_confirmed(v, cfg, led):
            die("Task verify command '%s' is not confirmed. Run: osr confirm-commands" % normalize_command(v))
        cmds.append(("task", v))
    for v in card.get("conformance", []):
        if v in cfg.get("commands", {}):
            if not confirmed(cfg, led, v):
                die("Conformance command '%s' is not confirmed. Run: osr confirm-commands" % v)
            cmds.append(("conformance", cfg["commands"][v]["cmd"]))
        else:
            if not is_verify_cmd_confirmed(v, cfg, led):
                die("Conformance command '%s' is not confirmed. Run: osr confirm-commands" % v)
            cmds.append(("conformance", v))
    results, ok = [], True
    for n, cmd in cmds:
        res = run_recorded(cmd, cfg, "%s-%s" % (tid, n))
        res["name"] = n
        results.append(res)
        ok = ok and res["ok"]
    cur2 = walk_tree(cfg)
    changed_during_run = diff_tree(cur_pre, cur2)
    if changed_during_run:
        ok = False
        print("GOVERNED CONTENT CHANGED DURING VERIFICATION: %s" % ", ".join(sorted(changed_during_run)))
        print("These bytes were not observed by a stable run. Run verification again on stable bytes (another run must observe the final tree).")
    r2 = run_check(cfg, st, tid, card, snap, cur2)
    if not r2["ok"] and r["ok"]:
        if not JSON_MODE:
            print("The verification run itself changed files outside scope or created flagged content:")
            print_check(r2)
        ok = False
    led.append("check", tid, ts["attempts"], ok=r2["ok"], fp=r2["fp"], flags=r2["flags"], unchecked=r2["refs"]["unchecked"][:30])
    start_entry = led.latest("start", tid, ts["attempts"])
    base = (start_entry.get("data") if start_entry else {}).get("baseline", {})
    red_green = {}
    for res in results:
        cmd_name = res["name"]
        prior = base.get(cmd_name)
        if prior:
            if not prior.get("ok") and res["ok"]:
                red_green[cmd_name] = "transitioned_to_green"
            elif prior.get("ok") and res["ok"]:
                red_green[cmd_name] = "preserved_green"
            else:
                red_green[cmd_name] = "failing"
    all_output_text = ""
    evidence_errors = []
    for res in results:
        log_name = res.get("log")
        recorded_sha = res.get("output_sha")
        log_p = ai("logs", log_name) if log_name else None
        if log_p is None or not log_p.is_file():
            evidence_errors.append("command '%s' has no retained log (%s)" % (res.get("name"), log_name))
            continue
        raw = log_p.read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if not recorded_sha or actual_sha != recorded_sha:
            evidence_errors.append(
                "log %s no longer matches its recorded output_sha (recorded %s, current %s)"
                % (log_name, recorded_sha, actual_sha)
            )
            continue
        if res.get("ok"):
            all_output_text += "\n" + raw.decode("utf-8", "replace")
    if evidence_errors:
        for err in evidence_errors:
            print("EVIDENCE INTEGRITY: %s" % err)
        die("Recorded command output was modified or is missing; it cannot be used as test evidence.", code=EXIT_INTEGRITY)
    canonical_tests, alias_tests = extract_test_identities(all_output_text)
    passed_tests = sorted(set(canonical_tests) | set(alias_tests))
    if card.get("negative_tests"):
        problems = []
        for neg in card["negative_tests"]:
            matched, reason = resolve_test_declaration(neg, canonical_tests)
            if reason != "ok":
                problems.append(named_test_message(neg, reason, matched, negative=True))
        if problems:
            ok = False
            for msg in problems:
                print("MISSING NEGATIVE TEST: %s" % msg)
        else:
            print("Negative tests verified: %s" % ", ".join(card["negative_tests"]))
    clean_results = [result_record(x) for x in results]
    led.append("verify", tid, ts["attempts"], ok=ok, fp=r2["fp"], start_seq=start_seq, results=clean_results, red_green=red_green, passed_tests=passed_tests, canonical_tests=canonical_tests)
    if not ok:
        ts["failures"] += 1
        save_state(st)
    if JSON_MODE:
        emit_json({
            "ok": ok,
            "exit_code": 0 if ok else 2,
            "status": "ok" if ok else "gate_failed",
            "task": tid,
            "failures": ts["failures"],
            "max_failures": cfg["max_inner_failures"],
            "results": clean_results,
            "red_green": red_green,
            "passed_tests": passed_tests,
            "canonical_tests": canonical_tests,
            "next": next_action()
        }, code=0 if ok else 2)
    print("\nVERIFY: %s" % ("PASS" if ok else "FAIL  (failures this attempt: %d/%d)" % (ts["failures"], cfg["max_inner_failures"])))
    print("NEXT: %s" % next_action())
    sys.exit(0 if ok else 2)


def cmd_review(a):
    cfg, st, led = ctx()
    ensure_plan_and_config_approved(st)
    tid, stage = a.task, a.stage
    ts = require_active(st, tid)
    require_not_failed_out(cfg, ts, tid)
    card, errs = validate_card(tid, cfg, parse_plan()[0])
    snap = load_snap(tid)
    cur = walk_tree(cfg)
    fp = fingerprint(diff_tree(snap, cur), cur)
    start_entry = led.latest("start", tid, ts["attempts"])
    if not start_entry:
        die("No start record exists for %s attempt %d. Run: osr start %s --model <name>" % (tid, ts["attempts"], tid))
    start_seq = start_entry["seq"]
    v = led.latest("verify", tid, ts["attempts"])
    if (not v or not v["data"].get("ok") or v["data"].get("fp") != fp
            or v["data"].get("start_seq") != start_seq):
        die("No passing verify for the CURRENT code and start lineage. Reviews only apply to verified code. Run: osr verify %s" % tid)
    if stage == "quality":
        s = led.latest("review", tid, ts["attempts"], "spec")
        if (not s or s["data"].get("verdict") != "PASS" or s["data"].get("fp") != fp
                or s["data"].get("start_seq") != start_seq):
            die("Spec review must pass (for the current code and start lineage) before the quality review.")
    rp = ai("reviews", "%s.%s.md" % (tid, stage))
    if not rp.exists():
        die("Write the review file first: %s  (template: assets/%s-review.md)" % (rp.relative_to(ROOT).as_posix(), stage))
    text = rp.read_text(encoding="utf-8")
    fsha = sha_text(text)
    for e in led.entries():
        if e["type"] == "review" and e["task"] == tid and e["data"].get("stage") == stage and e["data"].get("file_sha") == fsha:
            die("This review file is identical to one already recorded. Re-review the CURRENT code and write a fresh review.")
    if stage == "spec":
        errs, items, verdict = validate_spec_review(text, card["requirements"], parse_plan()[0])
    else:
        errs, items, verdict = validate_quality_review(text, card=card, plan=parse_plan()[0])
    if errs:
        print("REVIEW REJECTED (malformed or unsupported claims):")
        for e in errs:
            print("  - " + e)
        sys.exit(1)
    self_review = bool(ts["model"]) and ts["model"] == a.reviewer
    if self_review and cfg["require_distinct_reviewer"]:
        die("Config requires a reviewer different from the implementer (%s)." % ts["model"])
    if self_review:
        print("WARNING: reviewer == implementer (%s). Recorded as self-review (weaker assurance; shown in audit)." % a.reviewer)
    led.append("review", tid, ts["attempts"], stage=stage, verdict=verdict, fp=fp, start_seq=start_seq, file_sha=fsha, reviewer=a.reviewer, self_review=self_review, items=items)
    if verdict == "FAIL":
        ts["failures"] += 1
        save_state(st)
        print("REVIEW RECORDED: FAIL (failures this attempt: %d/%d). Fix the code, then osr verify %s and re-review." % (ts["failures"], cfg["max_inner_failures"], tid))
        sys.exit(1)
    print("REVIEW RECORDED: %s PASS" % stage)
    print("NEXT: %s" % next_action())


def build_completion(cfg, st, led, tid, ts, card, cur, start_entry):
    """Build one completion manifest from the recorded start and candidate result.

    The delta is derived from the start snapshot (the bytes the task began from)
    to the current tree. Scope, start lineage and the recomputed work fingerprint
    are checked here; the caller writes state and ledger under one lock.

    A genuine pre-feature start carries none of ``START_BINDING_KEYS``; under a
    legacy approval it closes as an explicit legacy technical closure (no
    invented ``osr.completion.v1`` fields). A partially bound start, or any start
    without bindings under a baseline-backed approval, is an error and never
    falls back to legacy.
    """
    sdata = start_entry.get("data") or {}
    start_seq = start_entry["seq"]
    approval = led.latest("plan_approved")
    epoch = approval["seq"] if approval else None
    adata = (approval or {}).get("data") or {}
    approval_has_baseline = all(k in adata for k in _APPROVAL_BASELINE_KEYS)
    present = [k for k in START_BINDING_KEYS if k in sdata]
    missing = [k for k in START_BINDING_KEYS if k not in sdata]
    legacy_start = not present

    card_path = ai("tasks", tid + ".md")
    card_sha = file_sha(card_path) if card_path.exists() else None
    plan_raw = file_sha(ai("PLAN.md"))
    cfg_sha = sha_config()
    ignore_sha = ignore_digest(cfg)

    if legacy_start and approval_has_baseline:
        die("Task %s's start record has no card/plan/baseline bindings, but the current approval epoch binds a governed baseline. "
            "A metadata-free start cannot be closed as legacy here; restart the task under the current baseline." % tid)
    if not legacy_start and missing:
        die("Task %s's start record is only partially bound (missing %s). New-format start metadata must be complete; "
            "malformed new evidence is never downgraded to legacy. Restore the start bytes or restart the task." % (
                tid, ", ".join(missing)))
    if not legacy_start:
        if card_sha != sdata.get("card_sha"):
            die("Task %s's card changed during the attempt. The originally recorded scope cannot expand silently; "
                "restore the card or start a new attempt." % tid)
        if plan_raw != sdata.get("plan_raw_sha") or cfg_sha != sdata.get("config_sha") or ignore_sha != sdata.get("ignore_sha"):
            die("PLAN.md, config.json or the governed ignore policy changed during the attempt. The human must re-approve and the task must restart.")
        if sdata.get("approval_epoch") != epoch:
            die("Task %s's start belongs to approval epoch %r, not the current epoch %r. Restart the task under the current approval."
                % (tid, sdata.get("approval_epoch"), epoch))
    snap = snapshot_map(tid)
    if snap is None:
        die("Task %s has no readable start snapshot. Restart the task." % tid)
    if not legacy_start and manifest_digest(snap) != sdata.get("start_snapshot_sha"):
        die("Task %s's start snapshot no longer matches its recorded digest. Stop and tell the human." % tid)
    if not legacy_start and sdata.get("approval_epoch") is not None and sdata.get("start_base_sha") is None:
        fresh = st.get("freshness")
        if isinstance(fresh, dict):
            die("Task %s started under a legacy epoch but the current approval has a baseline. Restart under the current baseline." % tid)
    result_map = manifest_from_tree(cur)
    delta, changed = task_delta(snap, result_map)
    for path in delta:
        if not matches(path, card.get("allowed_files", [])) or matches(path, card.get("forbidden_files", [])):
            die("Task %s's completion delta includes %s, outside the card's allowed_files." % (tid, path))
    fp = work_fingerprint(changed, result_map)
    v = led.latest("verify", tid, ts["attempts"])
    s = led.latest("review", tid, ts["attempts"], "spec")
    q = led.latest("review", tid, ts["attempts"], "quality")
    for e, label in ((v, "verify"), (s, "spec review"), (q, "quality review")):
        if not e or e["data"].get("start_seq") != start_seq:
            die("Task %s's %s does not belong to the current start lineage. Re-run it." % (tid, label))
    if not v["data"].get("ok") or v["data"].get("fp") != fp:
        die("The verified fingerprint does not describe the current bytes; run: osr verify %s" % tid)
    if s["data"].get("verdict") != "PASS" or s["data"].get("fp") != fp:
        die("The spec review does not describe the current bytes; re-run it on the verified code.")
    if q["data"].get("verdict") != "PASS" or q["data"].get("fp") != fp:
        die("The quality review does not describe the current bytes; re-run it on the verified code.")
    if legacy_start:
        closure = {
            "schema": LEGACY_CLOSURE_SCHEMA,
            "task": tid,
            "attempt": ts["attempts"],
            "start_seq": start_seq,
            "verify_seq": v["seq"],
            "spec_review_seq": s["seq"],
            "quality_review_seq": q["seq"],
            "verified_fp": v["data"]["fp"],
            "missing_bindings": missing,
            "reason": ("start seq %s predates the card/plan/config/base binding metadata and approval epoch %r "
                       "has no governed baseline" % (start_seq, epoch)),
        }
        return closure, fp
    completion = {
        "schema": COMPLETION_SCHEMA,
        "task": tid,
        "attempt": ts["attempts"],
        "approval_epoch": sdata.get("approval_epoch"),
        "plan_sha": plan_raw,
        "config_sha": cfg_sha,
        "ignore_sha": ignore_sha,
        "card_sha": card_sha,
        "inputs_sha": input_hash(card),
        "start_base_sha": sdata.get("start_base_sha"),
        "start_snapshot_sha": sdata.get("start_snapshot_sha"),
        "verified_fp": v["data"]["fp"],
        "verify_seq": v["seq"],
        "spec_review_seq": s["seq"],
        "quality_review_seq": q["seq"],
        "start_seq": start_seq,
        "delta": delta,
        "result_sha": manifest_digest(result_map),
        "path_count": len(delta),
    }
    return completion, fp


def cmd_done(a):
    cfg, st, led = ctx()
    ensure_plan_and_config_approved(st)
    tid = a.task
    ts = require_active(st, tid)
    card, errs = validate_card(tid, cfg, parse_plan()[0])
    gates, fp = gate_status(cfg, st, led, tid, card)
    bad = [(n, m) for n, ok, m in gates if not ok]
    for n, ok, m in gates:
        print("  [%s] %s %s" % ("x" if ok else " ", n, "" if ok else "- " + m))
    if bad:
        print("NOT DONE. Missing gates above. NEXT: %s" % next_action())
        sys.exit(1)
    start_entry = led.latest("start", tid, ts["attempts"])
    if not start_entry:
        die("No start record exists for %s attempt %d. Run: osr start %s --model <name>" % (tid, ts["attempts"], tid))
    completion, fp2 = build_completion(cfg, st, led, tid, ts, card, walk_tree(cfg), start_entry)
    if fp2 != fp:
        die("The completion delta does not reproduce the verified work fingerprint. Re-run: osr verify %s" % tid)
    with LedgerLock(timeout=0.3):
        current_st = load_state()
        current_ts = task_state(current_st, tid)
        if current_ts.get("status") != "in_progress" or current_ts.get("attempts") != ts["attempts"]:
            die("Task %s changed while done was waiting. Re-check the current state before completing." % tid)
        if completion.get("schema") == COMPLETION_SCHEMA:
            current_ts["completion"] = completion
            current_ts.pop("legacy_closure", None)
            current_ts["status"] = "done"
            save_state(current_st)
            led.append("done", tid, ts["attempts"], fp=fp, completion=completion)
        else:
            current_ts.pop("completion", None)
            current_ts["legacy_closure"] = completion
            current_ts["status"] = "done"
            save_state(current_st)
            led.append("done", tid, ts["attempts"], fp=fp, legacy_closure=completion)
    print("Task %s DONE (attempt %d)." % (tid, ts["attempts"]))
    if completion.get("schema") == COMPLETION_SCHEMA and completion.get("start_base_sha") is None:
        print("NOTE: this completion belongs to a legacy epoch with no baseline; the final audit will report it UNVERIFIED.")
    elif completion.get("schema") != COMPLETION_SCHEMA:
        print("NOTE: recorded as an explicit legacy technical closure (missing start bindings: %s). "
              "The final audit will report it UNVERIFIED with no requirement credit." % ", ".join(completion.get("missing_bindings") or []))
    print("NEXT: %s" % next_action())


def cmd_triage(a):
    cfg, st, led = ctx()
    tid = a.task
    ts = task_state(st, tid)
    if ts["attempts"] < 1 or ts["status"] == "done":
        die("Task %s has no active attempt to diagnose." % tid)
    if len(a.evidence) < 20 or len(a.change) < 15:
        die("Give concrete --evidence (20+ chars: what you observed) and --change (15+ chars: what will be different next attempt).")
    ts["triaged_attempt"] = ts["attempts"]
    ts["failures"] = 0
    ts["requires"] = {"layer": a.layer, "input_hash": ts["input_hash"], "model": ts["model"], "seq": led.entries()[-1]["seq"] + 1}
    if a.layer in ("spec", "plan"):
        ts["blocked"] = "%s fault: %s" % (a.layer, a.evidence[:160])
    save_state(st)
    led.append("triage", tid, ts["attempts"], layer=a.layer, evidence=a.evidence, change=a.change)
    msg = {
        "spec": "BLOCKED. Ask the human to clarify intent, update PLAN.md, and re-approve. Do not guess.",
        "plan": "BLOCKED. The decomposition is wrong. Propose a re-plan to the human (split or reorder tasks).",
        "prompt": "Rewrite the task card (one goal, explicit constraints, an example, a 'Do not' list), then start a new attempt.",
        "context": "Rebuild a minimal context packet (fix context_files), use a FRESH session that reloads .ai/ state, then start a new attempt.",
        "environment": "Fix the environment, run: osr env-check (must pass), then start a new attempt.",
        "model": "Start the next attempt with a different --model.",
        "implementation": "Plain implementation bug. Start a new attempt and fix the specific defect.",
    }[a.layer]
    print("Triage recorded (layer: %s). %s" % (a.layer, msg))


def cmd_unblock(a):
    cfg, st, led = ctx()
    check_approval_secret(cfg, a)
    ts = task_state(st, a.task)
    ts["blocked"] = None
    ts["extra_attempts"] += a.extra_attempts
    save_state(st)
    by_val = join_arg(a.by)
    led.append("unblock", a.task, ts["attempts"], by=by_val, note=a.note, extra_attempts=a.extra_attempts)
    print("Unblocked %s by %s." % (a.task, by_val))


def cmd_waive(a):
    cfg, st, led = ctx()
    flag = a.flag or getattr(a, "flag_pos", None)
    if not flag:
        die("Flag is required (either as positional argument or --flag).")
    a.flag = flag
    ts = task_state(st, a.task)
    if len(a.reason) < 15:
        die("A waiver needs a real reason (15+ chars).")
    kind = a.flag.split(":")[0]
    if kind in cfg["human_only_flags"] and not a.approved_by:
        die("'%s' flags need human approval. Ask the human, then add: --approved-by <name>" % kind)
    if kind in cfg.get("human_only_flags", []) or a.approved_by:
        check_approval_secret(cfg, a)
    st["waivers"].append({"task": a.task, "flag": a.flag, "reason": a.reason, "approved_by": a.approved_by})
    save_state(st)
    led.append("waive", a.task, ts["attempts"], flag=a.flag, reason=a.reason, approved_by=a.approved_by)
    print("Waiver recorded (visible in the final audit).")


def cmd_fixture_add(a):
    cfg, st, led = ctx()
    fp = ROOT / a.path
    if not fp.is_file():
        die("Fixture file '%s' does not exist." % a.path)
    try:
        rel_path = fp.relative_to(ROOT).as_posix()
    except Exception:
        rel_path = a.path.replace("\\", "/")
    content = fp.read_bytes()
    h = hashlib.sha256(content).hexdigest()
    st.setdefault("fixtures", {})
    st["fixtures"][rel_path] = {
        "sha256": h,
        "seam": a.seam,
        "source": a.source,
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_state(st)
    led.append("fixture_add", path=rel_path, seam=a.seam, source=a.source, sha256=h)
    if JSON_MODE:
        emit_json({"ok": True, "exit_code": 0, "status": "ok", "path": rel_path, "seam": a.seam, "sha256": h}, code=0)
    print("Fixture registered: %s (seam: %s, sha256: %s)" % (rel_path, a.seam, h))


def cmd_fixture_capture(a):
    cfg, st, led = ctx()
    ensure_approval_fresh(st)
    requested = normalize_command(a.cmd)
    actual_cmd = None
    # A configured name resolves to its confirmed actual command; a raw command
    # must itself be exactly confirmed. Either way only actual_cmd is executed.
    if requested and requested in cfg.get("commands", {}):
        if confirmed(cfg, led, requested):
            actual_cmd = normalize_command(cfg["commands"][requested].get("cmd"))
    elif requested and is_verify_cmd_confirmed(requested, cfg, led):
        actual_cmd = requested

    if not actual_cmd:
        die("Capture command '%s' is not confirmed. Run: osr confirm-commands or define it in .ai/config.json" % requested)

    code, text, secs, to = run_cmd(actual_cmd, cfg)
    if code != 0 or to:
        die("Fixture capture command failed (exit %s%s):\n%s" % (code, " TIMEOUT" if to else "", text))

    fp = ROOT / a.path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(text, encoding="utf-8")

    try:
        rel_path = fp.relative_to(ROOT).as_posix()
    except Exception:
        rel_path = a.path.replace("\\", "/")

    content = fp.read_bytes()
    h = hashlib.sha256(content).hexdigest()
    st.setdefault("fixtures", {})
    st["fixtures"][rel_path] = {
        "sha256": h,
        "seam": a.seam,
        "cmd": requested,
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_state(st)
    led.append("fixture_capture", path=rel_path, seam=a.seam, cmd=requested, sha256=h)
    if JSON_MODE:
        emit_json({"ok": True, "exit_code": 0, "status": "ok", "path": rel_path, "seam": a.seam, "cmd": requested, "sha256": h}, code=0)
    print("Fixture captured via '%s' -> %s (seam: %s, sha256: %s)" % (requested, rel_path, a.seam, h))


def cmd_signoff(a):
    cfg, st, led = ctx()
    check_approval_secret(cfg, a)
    plan, _ = parse_plan()
    if not plan or a.req not in plan:
        die("Unknown requirement %s" % a.req)
    by_val = join_arg(a.by)
    st["signoffs"][a.req] = {"by": by_val, "note": a.note, "ts": now()}
    save_state(st)
    led.append("signoff", None, None, req=a.req, by=by_val, note=a.note)
    print("%s signed off by %s." % (a.req, by_val))


def cmd_reset(a):
    cfg, st, led = ctx()
    check_approval_secret(cfg, a)
    st["tasks"][a.task] = task_state({"tasks": {}}, a.task)
    if snap_path(a.task).exists():
        snap_path(a.task).unlink()
    save_state(st)
    by_val = join_arg(a.by)
    led.append("reset", a.task, None, by=by_val, reason=a.reason)
    print("Task %s reset (history stays in the ledger)." % a.task)


def _completion_shape_errors(c):
    """Structural validation of one ``osr.completion.v1`` record."""
    if not isinstance(c, dict):
        return ["completion record is not an object"]
    errs = []
    if c.get("schema") != COMPLETION_SCHEMA:
        errs.append("schema is %r, expected %r" % (c.get("schema"), COMPLETION_SCHEMA))
    if not isinstance(c.get("task"), str) or not c.get("task"):
        errs.append("task is missing")
    if not isinstance(c.get("attempt"), int):
        errs.append("attempt is not an integer")
    if not isinstance(c.get("approval_epoch"), int):
        errs.append("approval_epoch is not an integer")
    for key in ("plan_sha", "config_sha", "ignore_sha", "card_sha", "start_snapshot_sha", "verified_fp", "result_sha"):
        if not valid_sha(c.get(key)):
            errs.append("%s is not a sha256 hex digest" % key)
    if "start_base_sha" not in c:
        errs.append("start_base_sha is missing")
    elif c.get("start_base_sha") is not None and not valid_sha(c.get("start_base_sha")):
        errs.append("start_base_sha is neither null nor a sha256 digest")
    for key in ("start_seq", "verify_seq", "spec_review_seq", "quality_review_seq", "path_count"):
        if not isinstance(c.get(key), int):
            errs.append("%s is not an integer" % key)
    delta = c.get("delta")
    if not isinstance(delta, dict):
        errs.append("delta is not an object")
    else:
        for path, value in delta.items():
            if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
                errs.append("delta path %r is not a safe relative path" % path)
            if value is not None and not valid_sha(value):
                errs.append("delta for %s is neither null nor a sha256 digest" % path)
        if isinstance(c.get("path_count"), int) and c["path_count"] != len(delta):
            errs.append("path_count does not equal the delta length")
    return errs


def _legacy_closure_errors(c):
    """Structural validation of one explicit legacy technical closure record.

    This is not a completion certificate: it carries no invented historical
    card/plan/base digests, only references to the records that exist and the
    binding keys that were genuinely absent.
    """
    if not isinstance(c, dict):
        return ["legacy closure record is not an object"]
    errs = []
    if c.get("schema") != LEGACY_CLOSURE_SCHEMA:
        errs.append("schema is %r, expected %r" % (c.get("schema"), LEGACY_CLOSURE_SCHEMA))
    if not isinstance(c.get("task"), str) or not c.get("task"):
        errs.append("task is missing")
    if not isinstance(c.get("attempt"), int):
        errs.append("attempt is not an integer")
    for key in ("start_seq", "verify_seq", "spec_review_seq", "quality_review_seq"):
        if not isinstance(c.get(key), int):
            errs.append("%s is not an integer" % key)
    if not valid_sha(c.get("verified_fp")):
        errs.append("verified_fp is not a sha256 hex digest")
    missing = c.get("missing_bindings")
    if (not isinstance(missing, list) or not missing
            or not all(isinstance(k, str) and k for k in missing)):
        errs.append("missing_bindings must list the absent start bindings")
    if not isinstance(c.get("reason"), str) or len(c.get("reason").strip()) < 15:
        errs.append("legacy reason is missing or too short")
    return errs


def evaluate_acceptance(cfg, st, led, plan=None, current_tree=None):
    """Derive the last accepted governed map, then compare it with the current tree.

    Acceptance lineage is deliberately separate from the final audit verdict:
    todo tasks, an active task and pending human requirements do not prevent
    deriving the accepted map. Historical deltas are replayed in completion
    order and each one is checked against the map that existed at that point;
    only the final map is compared with today's bytes.
    """
    result = {
        "failures": [], "unverified": [], "unverified_tasks": {}, "notes": [],
        "archived": [], "accepted": {}, "accepted_tasks": {}, "last_accepted_by": {},
        "epoch": None, "baseline": None, "legacy": False, "derivable": False,
        "tree_drift": [],
    }
    entries = led.entries()
    by_seq = {e["seq"]: e for e in entries}
    approval = led.latest("plan_approved")
    if approval is None:
        result["failures"].append("no plan_approved ledger entry exists")
        return result
    epoch = approval["seq"]
    result["epoch"] = epoch
    adata = approval.get("data") or {}
    fresh = st.get("freshness")
    baseline_keys = _APPROVAL_BASELINE_KEYS
    ledger_baseline = all(k in adata for k in baseline_keys)
    ledger_partial = any(k in adata for k in baseline_keys) and not ledger_baseline

    plan_path = ai("PLAN.md")
    plan_exists = plan_path.exists()
    current_plan_text = plan_path.read_text(encoding="utf-8") if plan_exists else ""
    current_plan_norm = sha_text(current_plan_text)
    current_plan_raw = file_sha(ai("PLAN.md")) if plan_exists else None
    current_cfg_sha = sha_config()
    current_ignore = ignore_digest(cfg)

    if st.get("plan_hash") != current_plan_norm:
        result["failures"].append("PLAN.md changed since approval; the human must run: osr approve-plan --by <name>")
    if adata.get("plan_hash") and adata.get("plan_hash") != current_plan_norm:
        result["failures"].append("the approved PLAN.md digest does not match the ledger approval record")
    if st.get("config_hash") and st.get("config_hash") != current_cfg_sha:
        result["failures"].append("config.json changed since plan approval; the human must re-run approve-plan")
    if adata.get("config_hash") and adata.get("config_hash") != current_cfg_sha:
        result["failures"].append("config.json does not match the ledger approval record")

    if ledger_partial:
        result["failures"].append("the plan_approved entry carries a partial baseline commitment; re-approval is required")
        return result

    if ledger_baseline:
        if adata.get("approval_epoch") != epoch:
            result["failures"].append("approval baseline epoch %r does not match approval entry seq %d" % (adata.get("approval_epoch"), epoch))
        if not isinstance(fresh, dict):
            result["failures"].append("the ledger binds an approval baseline but state.json has no freshness block; no automatic adoption")
            return result
        manifest = fresh.get("manifest")
        if not isinstance(manifest, dict):
            result["failures"].append("state freshness baseline manifest is missing or malformed")
            return result
        clean_manifest = {}
        for path, sha in manifest.items():
            if not isinstance(path, str) or not valid_sha(sha):
                result["failures"].append("state freshness manifest has an invalid entry %r" % path)
                continue
            clean_manifest[path] = sha
        if result["failures"]:
            return result
        state_manifest_sha = manifest_digest(clean_manifest)
        if fresh.get("epoch") != epoch:
            result["failures"].append("state freshness epoch %r does not match approval entry seq %d" % (fresh.get("epoch"), epoch))
        if fresh.get("manifest_sha") != state_manifest_sha or adata.get("manifest_sha") != state_manifest_sha:
            result["failures"].append("approval baseline manifest digest does not match its ledger commitment")
        if fresh.get("plan_raw_sha") != adata.get("plan_raw_sha"):
            result["failures"].append("approval plan representation digest differs between state and ledger")
        if current_plan_raw != adata.get("plan_raw_sha"):
            result["failures"].append("PLAN.md bytes changed since approval")
        if fresh.get("ignore_sha") != adata.get("ignore_sha") or current_ignore != adata.get("ignore_sha"):
            result["failures"].append("the governed ignore policy changed since approval")
        if fresh.get("config_sha") not in (None, adata.get("config_hash")) or adata.get("config_hash") != current_cfg_sha:
            result["failures"].append("config.json does not match the approval baseline")
        if result["failures"]:
            return result
        result["baseline"] = dict(clean_manifest)
        result["accepted"] = dict(clean_manifest)
        result["last_accepted_by"] = {p: "(approval baseline)" for p in clean_manifest}
        result["derivable"] = True
        result["notes"].append("approval epoch %d baseline: %d governed files" % (epoch, len(clean_manifest)))
    else:
        if isinstance(fresh, dict):
            result["failures"].append("state.json records an approval baseline that the ledger does not bind; no automatic adoption")
            return result
        result["legacy"] = True
        result["notes"].append("approval epoch %d is legacy: no governed baseline was captured, so completions cannot be verified" % epoch)

    ids = set(task_ids())
    latest_reset = {}
    for e in entries:
        if e.get("type") == "reset" and e.get("task"):
            latest_reset[e["task"]] = max(latest_reset.get(e["task"], 0), e["seq"])

    lineage, archived = [], []
    for e in entries:
        if e.get("type") != "done":
            continue
        tid = e.get("task")
        if tid in ids and e["seq"] > latest_reset.get(tid, 0):
            lineage.append(e)
        else:
            archived.append(e)
    for e in archived:
        result["archived"].append("%s attempt %s at seq %d is archived history; it supplies no current requirement credit" % (
            e.get("task"), e.get("attempt"), e["seq"]))

    seen = {}
    lineage_ok = True
    running = dict(result["accepted"])

    for e in lineage:
        tid = e.get("task")
        attempt = e.get("attempt")
        label = "%s attempt %s" % (tid, attempt)
        ts = state_task(st, tid)
        if (tid, attempt) in seen:
            result["failures"].append("%s has more than one done record in the current lineage (conflicting/interrupted write)" % label)
            lineage_ok = False
            continue
        seen[(tid, attempt)] = e
        if ts.get("status") != "done":
            result["failures"].append("%s has a ledger done record but state.json is %r (interrupted write)" % (label, ts.get("status")))
            lineage_ok = False
        if ts.get("attempts") != attempt:
            result["failures"].append("%s ledger attempt does not match state attempts %r" % (label, ts.get("attempts")))
            lineage_ok = False
        completion = (e.get("data") or {}).get("completion")
        state_completion = ts.get("completion")
        if completion is None:
            closure = (e.get("data") or {}).get("legacy_closure")
            state_closure = ts.get("legacy_closure")
            if state_completion is not None:
                result["failures"].append("%s state.json has a completion mirror but the ledger done record does not (interrupted/mismatched write)" % label)
                lineage_ok = False
            elif closure is None and state_closure is None:
                reason = "%s has no completion manifest (legacy evidence); re-complete it under the current approval" % label
                result["unverified"].append(reason)
                result["unverified_tasks"][tid] = reason
                lineage_ok = False
            else:
                cerrs = []
                if closure is None or state_closure is None:
                    cerrs.append("only one of state.json/ledger carries the legacy closure")
                else:
                    if state_closure != closure:
                        cerrs.append("state.json legacy closure mirror disagrees with the ledger")
                    cerrs += _legacy_closure_errors(closure)
                    if not result["legacy"]:
                        cerrs.append("a legacy closure exists although the current approval epoch binds a governed baseline")
                if cerrs:
                    result["failures"].append("%s legacy closure is malformed: %s" % (label, "; ".join(cerrs)))
                    lineage_ok = False
                else:
                    refs_ok = True
                    c_start = closure.get("start_seq")
                    c_ver = closure.get("verify_seq")
                    c_spec = closure.get("spec_review_seq")
                    c_qual = closure.get("quality_review_seq")
                    c_fp = closure.get("verified_fp")
                    start_e = by_seq.get(c_start)
                    if (not start_e or start_e.get("type") != "start"
                            or start_e.get("task") != tid or start_e.get("attempt") != attempt):
                        result["failures"].append("%s legacy closure start_seq %r does not name this task's start" % (label, c_start))
                        refs_ok = False
                    ver = by_seq.get(c_ver)
                    if (not ver or ver.get("type") != "verify" or ver.get("task") != tid
                            or ver.get("attempt") != attempt or (ver.get("data") or {}).get("ok") is not True
                            or (ver.get("data") or {}).get("start_seq") != c_start
                            or (ver.get("data") or {}).get("fp") != c_fp):
                        result["failures"].append("%s legacy closure verify_seq %r does not name this attempt's passing verify for the closure fingerprint" % (label, c_ver))
                        refs_ok = False
                    for seq, stage in ((c_spec, "spec"), (c_qual, "quality")):
                        rev = by_seq.get(seq)
                        if (not rev or rev.get("type") != "review" or rev.get("task") != tid
                                or rev.get("attempt") != attempt
                                or (rev.get("data") or {}).get("stage") != stage
                                or (rev.get("data") or {}).get("verdict") != "PASS"
                                or (rev.get("data") or {}).get("start_seq") != c_start
                                or (rev.get("data") or {}).get("fp") != c_fp):
                            result["failures"].append("%s legacy closure %s_review_seq %r does not name this attempt's passing %s review for the closure fingerprint" % (label, stage, seq, stage))
                            refs_ok = False
                    if not (isinstance(c_start, int) and isinstance(c_ver, int)
                            and isinstance(c_spec, int) and isinstance(c_qual, int)
                            and c_start < c_ver < c_spec < c_qual < e["seq"]):
                        result["failures"].append("%s legacy closure evidence order is invalid (start < verify < spec < quality < done required)" % label)
                        refs_ok = False
                    if refs_ok:
                        reason = (
                            "%s is an explicit legacy technical closure: start seq %s predates the card/plan/config/base "
                            "bindings (%s) and its approval epoch has no governed baseline. The referenced verify (seq %s) "
                            "and reviews (%s, %s) are current for traceability but earn no requirement credit; re-complete "
                            "under a baseline-backed approval to verify." % (
                                label, c_start, ", ".join(closure.get("missing_bindings") or []),
                                c_ver, c_spec, c_qual))
                        result["unverified"].append(reason)
                        result["unverified_tasks"][tid] = reason
                lineage_ok = False
            continue
        shape = _completion_shape_errors(completion)
        if shape:
            result["failures"].append("%s completion record is malformed: %s" % (label, "; ".join(shape)))
            lineage_ok = False
            continue
        if completion.get("task") != tid or completion.get("attempt") != attempt:
            result["failures"].append("%s completion is bound to %s attempt %s" % (label, completion.get("task"), completion.get("attempt")))
            lineage_ok = False
            continue
        if state_completion is None:
            result["failures"].append("%s state.json is missing the completion mirror (interrupted write)" % label)
            lineage_ok = False
            continue
        if state_completion != completion:
            result["failures"].append("%s state.json completion mirror disagrees with the ledger (interrupted/tampered write)" % label)
            lineage_ok = False
            continue
        if completion.get("approval_epoch") != epoch:
            result["failures"].append("%s completion belongs to approval epoch %r, not current epoch %d (stale after re-approval)" % (
                label, completion.get("approval_epoch"), epoch))
            lineage_ok = False
            continue
        if completion.get("plan_sha") != current_plan_raw:
            result["failures"].append("%s completion is stale for the current PLAN.md bytes" % label)
            lineage_ok = False
        if completion.get("config_sha") != current_cfg_sha:
            result["failures"].append("%s completion is stale for the current config.json" % label)
            lineage_ok = False
        if completion.get("ignore_sha") != current_ignore:
            result["failures"].append("%s completion is stale for the current governed ignore policy" % label)
            lineage_ok = False
        card_path = ai("tasks", "%s.md" % tid)
        if not card_path.exists() or completion.get("card_sha") != file_sha(card_path):
            result["failures"].append("%s task card changed since completion; the recorded scope is stale" % label)
            lineage_ok = False

        start_seq = completion.get("start_seq")
        vseq = completion.get("verify_seq")
        sseq = completion.get("spec_review_seq")
        qseq = completion.get("quality_review_seq")
        start_e = by_seq.get(start_seq)
        if not start_e or start_e.get("type") != "start" or start_e.get("task") != tid or start_e.get("attempt") != attempt:
            result["failures"].append("%s completion start_seq %r does not name this task's start" % (label, start_seq))
            lineage_ok = False
        if not (isinstance(start_seq, int) and isinstance(vseq, int) and isinstance(sseq, int) and isinstance(qseq, int)
                and start_seq < vseq < sseq < qseq < e["seq"]):
            result["failures"].append("%s evidence order is invalid (start < verify < spec < quality < done required)" % label)
            lineage_ok = False
        if start_e and (start_e.get("data") or {}).get("approval_epoch") != epoch:
            result["failures"].append("%s start was recorded under a different approval epoch" % label)
            lineage_ok = False
        if start_e:
            sdata = start_e.get("data") or {}
            if sdata.get("card_sha") != completion.get("card_sha"):
                result["failures"].append("%s completion card digest does not match its start" % label)
                lineage_ok = False
            if sdata.get("start_snapshot_sha") != completion.get("start_snapshot_sha"):
                result["failures"].append("%s completion snapshot digest does not match its start" % label)
                lineage_ok = False
            if sdata.get("start_base_sha") != completion.get("start_base_sha"):
                result["failures"].append("%s completion base digest does not match its start" % label)
                lineage_ok = False

        ver = by_seq.get(vseq)
        if not ver or ver.get("type") != "verify" or ver.get("task") != tid or ver.get("attempt") != attempt:
            result["failures"].append("%s completion verify_seq %r does not name this attempt's verify" % (label, vseq))
            lineage_ok = False
        else:
            vdata = ver.get("data") or {}
            if vdata.get("ok") is not True:
                result["failures"].append("%s references a failing verify record" % label)
                lineage_ok = False
            if vdata.get("fp") != completion.get("verified_fp"):
                result["failures"].append("%s verified_fp does not match the referenced verify fingerprint" % label)
                lineage_ok = False
            if vdata.get("start_seq") != start_seq:
                result["failures"].append("%s verify record belongs to a different start lineage" % label)
                lineage_ok = False
        for seq, stage in ((sseq, "spec"), (qseq, "quality")):
            rev = by_seq.get(seq)
            if (not rev or rev.get("type") != "review" or rev.get("task") != tid
                    or rev.get("attempt") != attempt or (rev.get("data") or {}).get("stage") != stage):
                result["failures"].append("%s completion %s_review_seq %r does not name this attempt's %s review" % (label, stage, seq, stage))
                lineage_ok = False
                continue
            rdata = rev.get("data") or {}
            if rdata.get("verdict") != "PASS":
                result["failures"].append("%s %s review is not PASS" % (label, stage))
                lineage_ok = False
            if rdata.get("fp") != completion.get("verified_fp"):
                result["failures"].append("%s %s review fingerprint does not match verified_fp" % (label, stage))
                lineage_ok = False
            if rdata.get("start_seq") != start_seq:
                result["failures"].append("%s %s review belongs to a different start lineage" % (label, stage))
                lineage_ok = False

        snap = snapshot_map(tid)
        if result["legacy"]:
            # A legacy epoch has no committed baseline, so it cannot reconstruct
            # an unattested start map. Never adopt the current tree.
            if snap is None:
                result["failures"].append("%s start snapshot is missing or unreadable (legacy evidence cannot be reconstructed from a baseline)" % label)
                lineage_ok = False
                continue
            if manifest_digest(snap) != completion.get("start_snapshot_sha"):
                result["failures"].append("%s start snapshot does not match its recorded digest (interrupted/tampered)" % label)
                lineage_ok = False
        else:
            # A baseline-backed replay reconstructs the expected start map from
            # the committed baseline plus validated predecessor deltas. A local
            # snapshot is only an optional cache: when present it must agree,
            # but it never overrides the bound map.
            if snap is not None and manifest_digest(snap) != completion.get("start_snapshot_sha"):
                result["failures"].append("%s local start snapshot cache disagrees with the bound start snapshot digest; the cached bytes are not authoritative" % label)
                lineage_ok = False

        delta = completion.get("delta") or {}
        card = parse_card(tid) if card_path.exists() else {k: [] for k in CARD_KEYS}
        # A baseline-backed epoch replays onto the running accepted map, which is
        # also the task's expected start map. A legacy epoch uses its recorded
        # start snapshot; the completion is still checked for internal
        # consistency but can never supply current requirement credit.
        pre = dict(snap) if result["legacy"] else dict(running)
        applied = {}
        for path in sorted(delta):
            value = delta[path]
            if not matches(path, card.get("allowed_files", [])) or matches(path, card.get("forbidden_files", [])):
                result["failures"].append("%s delta path %s is outside the recorded card scope" % (label, path))
                lineage_ok = False
            if value is None:
                if path not in pre:
                    result["failures"].append("%s deletes %s but it was not present in the accepted map" % (label, path))
                    lineage_ok = False
                applied[path] = "D"
                pre.pop(path, None)
            else:
                applied[path] = "A" if path not in pre else "M"
                pre[path] = value
        if completion.get("path_count") != len(delta):
            result["failures"].append("%s path_count %r does not equal the %d delta entries" % (label, completion.get("path_count"), len(delta)))
            lineage_ok = False
        if manifest_digest(pre) != completion.get("result_sha"):
            result["failures"].append("%s result_sha does not describe the delta applied to the accepted map" % label)
            lineage_ok = False
        if work_fingerprint(applied, pre) != completion.get("verified_fp"):
            result["failures"].append("%s completion manifest does not describe the verified bytes (fingerprint mismatch)" % label)
            lineage_ok = False

        if result["legacy"]:
            reason = "%s completion belongs to a legacy approval epoch with no governed baseline" % label
            if reason not in result["unverified"]:
                result["unverified"].append(reason)
            result["unverified_tasks"][tid] = reason
            lineage_ok = False
            continue

        if completion.get("start_base_sha") is None:
            result["failures"].append("%s has no start base although the approval epoch has a baseline" % label)
            lineage_ok = False
            continue
        if completion.get("start_base_sha") != completion.get("start_snapshot_sha"):
            result["failures"].append("%s start snapshot does not equal the accepted base at start" % label)
            lineage_ok = False
        if completion.get("start_base_sha") != manifest_digest(running):
            result["failures"].append("%s started from a map that is not the running accepted map (pre-start drift)" % label)
            lineage_ok = False

        running = pre
        result["accepted"] = dict(running)
        if lineage_ok:
            result["accepted_tasks"][tid] = attempt
            for path in delta:
                result["last_accepted_by"][path] = tid

    current_lineage_tasks = {e.get("task") for e in lineage}
    for tid in sorted(ids):
        ts = state_task(st, tid)
        if ts.get("status") == "done" and tid not in current_lineage_tasks:
            result["failures"].append("%s state.json is done but the current ledger lineage has no done record (interrupted write)" % tid)
            lineage_ok = False

    if result["legacy"]:
        return result
    if not lineage_ok:
        return result

    result["derivable"] = True
    if current_tree is None:
        current_tree = walk_tree(cfg)
    current_map = manifest_from_tree(current_tree)
    accepted = result["accepted"]
    for path in sorted(set(accepted) | set(current_map)):
        if path not in accepted:
            result["tree_drift"].append("added governed file %s after the accepted set" % path)
        elif path not in current_map:
            owner = result["last_accepted_by"].get(path, "a completed task")
            result["tree_drift"].append("deleted governed file %s (last accepted by %s)" % (path, owner))
        elif accepted[path] != current_map[path]:
            owner = result["last_accepted_by"].get(path, "a completed task")
            result["tree_drift"].append("modified governed file %s (last accepted by %s)" % (path, owner))
    if result["tree_drift"]:
        result["failures"].extend(result["tree_drift"])
    return result


def requirement_rows(cfg, st, led, plan, accepted=None, unverified=None):
    unverified = unverified or {}
    rows = []
    ids = task_ids()
    cards = {t: parse_card(t) for t in ids}
    for r, v in plan.items():
        tasks = [t for t in ids if r in cards[t]["requirements"]]
        status, ev = "UNCOVERED", ""
        if v.get("check") == "manual":
            if r in st.get("signoffs", {}):
                status, ev = "HUMAN-SIGNED", st["signoffs"][r]["by"]
            else:
                status = "PENDING-HUMAN (UNVERIFIED)"
                ev = v.get("script") or "manual test script required"
        elif tasks:
            if any(task_state(st, t)["status"] != "done" for t in tasks):
                status = "INCOMPLETE"
            elif accepted is not None and any(t not in accepted for t in tasks):
                blocked = next(t for t in tasks if t not in accepted)
                status = "UNVERIFIED"
                ev = unverified.get(blocked) or "%s has no current accepted completion" % blocked
            else:
                statuses = []
                for t in tasks:
                    attempt = accepted[t] if accepted is not None else task_state(st, t)["attempts"]
                    e = led.latest("review", t, attempt, "spec")
                    if e:
                        statuses.append((e["data"].get("items") or {}).get(r, {}))
                if any(s.get("status") == "PASS" for s in statuses) and v["check"] == "auto":
                    status = "VERIFIED"
                    ev = next(s["evidence"] for s in statuses if s.get("status") == "PASS")
                    test_tags = []
                    for ac in v.get("ac", []):
                        test_tags += acceptance_test_tags(ac)
                    if test_tags:
                        ev += " (tests: %s)" % ", ".join(test_tags)
                elif r in st.get("signoffs", {}):
                    status, ev = "HUMAN-SIGNED", st["signoffs"][r]["by"]
                else:
                    status = "PENDING-HUMAN"
        rows.append((r, v["text"], v["check"], ",".join(tasks) or "-", status, ev))
    return rows


def cmd_coverage(a):
    cfg, st, led = ctx()
    plan, errs = parse_plan()
    if errs:
        die("\n".join(errs))
    for r in requirement_rows(cfg, st, led, plan):
        print("%-5s %-13s tasks=%-10s check=%-6s %s" % (r[0], r[4], r[3], r[2], r[1][:70]))


def cmd_audit(a):
    cfg, st, led = ctx()
    anchor_p = Path(a.anchor).resolve() if getattr(a, "anchor", None) else None
    if anchor_p is not None or (ROOT / ".osr-anchor").exists():
        ok, msg = led.verify_chain(anchor_path=anchor_p)
        if not ok:
            print("AUDIT: FAIL (ledger integrity check failed: %s)" % msg)
            sys.exit(1)
    plan, errs = parse_plan()
    if errs:
        die("Plan invalid:\n  " + "\n  ".join(errs))
    check_only = bool(getattr(a, "check", False))
    freshness = evaluate_acceptance(cfg, st, led, plan)
    rows = requirement_rows(
        cfg, st, led, plan,
        accepted=freshness["accepted_tasks"],
        unverified=freshness["unverified_tasks"],
    )
    ids = task_ids()
    notdone = [t for t in ids if task_state(st, t)["status"] != "done"]
    plan_ok = st["plan_hash"] == sha_text(ai("PLAN.md").read_text(encoding="utf-8"))
    lines = ["# Audit  (%s)" % now(), "", "Ledger integrity: ok. Plan approved and unchanged: %s." % plan_ok, "", "## Freshness", ""]
    if freshness["epoch"] is not None:
        lines.append("- Approval epoch: %d" % freshness["epoch"])
    if freshness["legacy"]:
        lines.append("- Baseline: legacy (no governed baseline was captured for this approval epoch)")
    elif freshness["baseline"] is not None:
        lines.append("- Baseline: %d governed files, digest %s" % (
            len(freshness["baseline"]), manifest_digest(freshness["baseline"])))
    if freshness["derivable"] and not freshness["legacy"]:
        lines.append("- Accepted map: %d governed files, digest %s" % (
            len(freshness["accepted"]), manifest_digest(freshness["accepted"])))
    for note in freshness["notes"]:
        lines.append("- %s" % note)
    if freshness["failures"]:
        lines += ["", "### Stale or malformed evidence (FAIL)"] + ["- " + f for f in freshness["failures"]]
    if freshness["unverified"]:
        lines += ["", "### Unverified evidence (no current requirement credit)"] + ["- " + u for u in freshness["unverified"]]
    if freshness["archived"]:
        lines += ["", "### Archived history (disclosed, no current credit)"] + ["- " + a_line for a_line in freshness["archived"]]
    lines += ["", "## Requirement traceability", "",
              "| Req | Check | Tasks | Status | Evidence |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s |" % (r[0], r[2], r[3], r[4], r[5] or ""))
    if notdone:
        lines += ["", "## Tasks not done", ", ".join(notdone)]
    if st["waivers"]:
        lines += ["", "## Waivers (decisions to bypass a flag)"]
        lines += ["- %s %s: %s (approved by %s)" % (w["task"], w["flag"], w["reason"], w["approved_by"] or "AI only") for w in st["waivers"]]
    selfrev = [e for e in led.entries() if e["type"] == "review" and e["data"].get("self_review")]
    if selfrev:
        lines += ["", "## Self-reviewed (implementer == reviewer)", ", ".join(sorted({e["task"] for e in selfrev}))]
    unchecked = set()
    for t in ids:
        e = led.latest("check", t, task_state(st, t)["attempts"])
        if e:
            unchecked |= set(e["data"].get("unchecked", []))
    if unchecked:
        lines += ["", "## References with no mechanical check (UNVERIFIED)"] + ["- " + u for u in sorted(unchecked)[:40]]
    seam_unverified = []
    for t in ids:
        c = parse_card(t)
        if c.get("fixtures"):
            conf_entries = [e for e in led.entries() if e.get("task") == t and e.get("type") == "verify" and e.get("data", {}).get("ok")]
            has_conf = False
            for ve in conf_entries:
                for res in ve.get("data", {}).get("results", []):
                    if res.get("name") == "conformance":
                        has_conf = True
                        break
            if not has_conf:
                seams_list = ", ".join(c.get("seams", [])) or "unnamed seam"
                seam_unverified.append("Task %s seam(s) '%s': declared fixtures %s without confirmed conformance run" % (
                    t, seams_list, ", ".join(c.get("fixtures", []))
                ))
    if seam_unverified:
        lines += ["", "## Seams with missing conformance (UNVERIFIED)"] + ["- " + s for s in seam_unverified]
    if not check_only:
        ai("AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    bad = ([r for r in rows if r[4] in ("UNCOVERED", "INCOMPLETE")] or notdone or not plan_ok
           or bool(freshness["failures"]))
    pending = [r[0] for r in rows if "PENDING-HUMAN" in r[4] or "UNVERIFIED" in r[4]]
    pending += freshness["unverified"]
    if seam_unverified:
        pending.append("seams-conformance")
    if bad:
        print("\nAUDIT: FAIL (gaps above)")
        sys.exit(1)
    if pending:
        print("\nAUDIT: COMPLETE WITH HUMAN REVIEW PENDING for: %s" % ", ".join(pending))
        sys.exit(2)
    print("\nAUDIT: PASS (every requirement has machine evidence or human sign-off)")


def cmd_status(a):
    cfg, st, led = ctx()
    ok, msg = led.verify_chain()
    plan_ok = st["plan_hash"] == sha_text(ai("PLAN.md").read_text(encoding="utf-8"))
    cfg_ok = not st.get("config_hash") or st.get("config_hash") == sha_config()
    lines = ["# State", "", "Ledger: %s" % msg]
    if not plan_ok:
        lines.append("Plan: VOIDED (PLAN.md changed since approval)")
    elif not cfg_ok:
        lines.append("Config: VOIDED (config.json changed since plan approval)")
    lines.append("")
    for t in task_ids():
        ts = task_state(st, t)
        lines.append("- %s: %s (attempt %d, failures %d)%s" % (t, ts["status"], ts["attempts"], ts["failures"], " BLOCKED: " + ts["blocked"] if ts["blocked"] else ""))
    lines += ["", "NEXT: " + next_action()]
    ai("STATE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def cmd_next(a):
    act = next_action()
    if JSON_MODE:
        emit_json({"ok": True, "exit_code": 0, "status": "ok", "action": act}, code=0)
    print(act)


def cmd_anchor(a):
    anchor_arg = getattr(a, "out", None) or getattr(a, "file", None)
    anchor_path = Path(anchor_arg).resolve() if anchor_arg else (ROOT / ".osr-anchor")
    led = Ledger()
    es = led.entries()
    if not es:
        die("Cannot anchor an empty ledger.", code=EXIT_USER_ERR)
    head = es[-1]
    data = {
        "seq": head["seq"],
        "head_hash": head["hash"],
        "hash": head["hash"],
        "ts": head.get("ts", now()),
    }
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if JSON_MODE:
        emit_json({"ok": True, "exit_code": 0, "status": "ok", "anchor_file": str(anchor_path), "head_hash": head["hash"], "seq": head["seq"]}, code=0)
    print("Ledger anchored to %s at seq %d (%s)." % (anchor_path.name, head["seq"], head["hash"][:12]))


def cmd_ledger_verify(a):
    anchor_p = Path(a.anchor).resolve() if getattr(a, "anchor", None) else None
    ok, msg = Ledger().verify_chain(anchor_path=anchor_p)
    if JSON_MODE:
        emit_json({"ok": ok, "exit_code": 0 if ok else 4, "status": "ok" if ok else "integrity_violation", "message": msg}, code=0 if ok else 4)
    print("LEDGER: %s" % msg)
    sys.exit(0 if ok else 4)


def cmd_review_pack(a):
    cfg, st, led = ctx()
    tid = a.task
    plan, perrs = parse_plan()
    card, errs = validate_card(tid, cfg, plan)
    if errs:
        die("Task card invalid:\n  " + "\n  ".join(errs))

    snap = load_snap(tid)
    cur = walk_tree(cfg)
    diff_map = diff_tree(snap, cur)

    diff_lines = []
    res = subprocess.run(["git", "diff"], capture_output=True, text=True, cwd=str(ROOT))
    if res.returncode == 0 and res.stdout.strip():
        diff_lines.append(res.stdout.strip())

    for path_str, status in sorted(diff_map.items()):
        p = ROOT / path_str
        if status == "A" and p.exists():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                diff_lines.append(f"diff --git a/{path_str} b/{path_str}\nnew file mode 100644\n--- /dev/null\n+++ b/{path_str}\n" + "\n".join("+" + l for l in content.splitlines()))
            except Exception:
                diff_lines.append(f"diff --git a/{path_str} b/{path_str} (new file)")
        elif status == "D":
            diff_lines.append(f"diff --git a/{path_str} b/{path_str}\ndeleted file mode 100644\n--- a/{path_str}\n+++ /dev/null")
        elif status == "M" and (res.returncode != 0 or not res.stdout.strip()) and p.exists():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                diff_lines.append(f"diff --git a/{path_str} b/{path_str}\n" + content)
            except Exception:
                diff_lines.append(f"diff --git a/{path_str} b/{path_str} (modified)")

    diff_content = "\n\n".join(diff_lines) if diff_lines else "(No diff)"

    req_lines = []
    for r in card.get("requirements", []):
        rinfo = plan.get(r, {})
        req_lines.append(f"- **{r}**: {rinfo.get('title', '')}")
        for ac in rinfo.get("ac", []):
            req_lines.append(f"  - AC: {ac}")

    card_path = ai("tasks", f"{tid}.md")
    card_raw = card_path.read_text(encoding="utf-8") if card_path.exists() else ""

    adversarial_prompt = (
        "> **Adversarial Review Directive**:\n"
        "> For every external field, find its definition in the provided source. "
        "Report any field the code uses that the source does not declare. "
        "Do not trust the builder's explanation."
    )

    seam_sections = []
    declared_seams = card.get("seams", [])
    if declared_seams and plan and getattr(plan, "seams", None):
        seam_sections.append("## Declared Seams")
        seam_sections.append("| seam id | consumer | provider | authoritative source | how it is checked |")
        seam_sections.append("|---|---|---|---|---|")
        for s in declared_seams:
            sinfo = plan.seams.get(s, {})
            seam_sections.append("| %s | %s | %s | %s | %s |" % (
                s, sinfo.get("consumer", ""), sinfo.get("provider", ""), sinfo.get("source", ""), sinfo.get("how", "")
            ))
        seam_sections.append("")
        seam_sections.append("## Authoritative Upstream Sources")
        for s in declared_seams:
            sinfo = plan.seams.get(s, {})
            src = sinfo.get("source", "").strip()
            if src:
                sp = ROOT / src
                if sp.is_file():
                    content = sp.read_text(encoding="utf-8", errors="replace")
                    seam_sections.append(f"### {s} (`{src}`)\n```\n{content}\n```\n")

    pack_sections = [
        f"# Review Pack: {tid}",
        "",
        adversarial_prompt,
        "",
        "## Acceptance Criteria",
        "\n".join(req_lines) if req_lines else "(None specified)",
        "",
        "## Task Specification",
        card_raw,
        "",
    ]
    if seam_sections:
        pack_sections += seam_sections + [""]
    pack_sections += [
        "## Code Diff",
        "```diff",
        diff_content,
        "```",
    ]
    pack_text = "\n".join(pack_sections) + "\n"

    if getattr(a, "out", None):
        out_p = Path(a.out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(pack_text, encoding="utf-8")

    if JSON_MODE:
        emit_json({
            "ok": True,
            "exit_code": 0,
            "status": "ok",
            "task": tid,
            "requirements": card.get("requirements", []),
            "diff": diff_content,
            "card": card_raw
        }, code=0)
    print(pack_text)


def cmd_quick(a):
    cfg, st, led = ctx(require_chain=True)
    ensure_approval_fresh(st)
    verify_cmd = normalize_command(a.verify)
    if not verify_cmd:
        die("Quick verify needs a non-empty command.", code=EXIT_USER_ERR)
    if a.allowed:
        allowed_pats = [pt.strip() for pt in a.allowed.split(",") if pt.strip()]
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(ROOT))
        if res.returncode == 0:
            changed = []
            for line in res.stdout.splitlines():
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    changed.append(parts[1].replace("\\", "/").strip('"\''))
        else:
            cur = walk_tree(cfg)
            changed = [f for f in cur.keys() if not f.startswith(".ai/")]

        for f in changed:
            if not matches(f, allowed_pats):
                die("Scope violation: file '%s' is outside allowed files (%s)" % (f, a.allowed), code=EXIT_USER_ERR)

    if TRIVIAL_CMD.match(verify_cmd):
        die("Quick verify command '%s' cannot prove anything." % verify_cmd, code=EXIT_USER_ERR)
    if WEAK_VERIFY_PAT.search(verify_cmd):
        die("Quick verify command '%s' is a weak verify command (token existence check, not a test)." % verify_cmd, code=EXIT_USER_ERR)
    if not is_verify_cmd_confirmed(verify_cmd, cfg, led):
        die("Quick verify command '%s' is not confirmed. Run: osr confirm-commands" % verify_cmd, code=EXIT_USER_ERR)
    if cfg.get("allow_no_commands") and not JSON_MODE:
        print("NOTE: allow_no_commands compatibility mode; execution is permitted but is not command-confirmed evidence.")

    res = run_recorded(verify_cmd, cfg, "quick")
    if not res["ok"]:
        if JSON_MODE:
            emit_json({"ok": False, "exit_code": 2, "status": "gate_failed", "cmd": a.verify, "log": res.get("log")}, code=2)
        print("QUICK VERIFY: FAIL")
        sys.exit(2)

    led.append("quick_verify", cmd=verify_cmd, allowed=a.allowed, ok=True)
    if JSON_MODE:
        emit_json({"ok": True, "exit_code": 0, "status": "ok", "cmd": verify_cmd, "allowed": a.allowed}, code=0)
    print("QUICK VERIFY: PASS")


def main():
    global ROOT, JSON_MODE
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="output structured JSON")

    class CustomParser(argparse.ArgumentParser):
        def error(self, message):
            if "--json" in sys.argv:
                emit_json({"ok": False, "exit_code": 1, "error": message, "status": "error"}, code=1)
            super().error(message)

    ap = CustomParser(prog="osr", parents=[common], description="Orchestrator-Supervisor-Reviewer enforcement CLI")
    ap.add_argument("--root", default=None, help="project root (default: current directory)")
    ap.add_argument("--version", action="version", version=VERSION)
    sp = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, parents=(), **kw):
        p = sp.add_parser(name, parents=[common] + list(parents), **kw)
        p.set_defaults(fn=fn)
        return p

    add("init", cmd_init, help="create .ai/ in the project")
    add("detect", cmd_detect, help="guess build/test/lint commands from marker files")
    add("confirm-commands", cmd_confirm, help="run configured commands and record which really work")
    add("env-check", cmd_env_check, help="re-run smoke commands after an environment fix")
    add("plan-check", cmd_plan_check, help="validate PLAN.md")
    p = add("approve-plan", cmd_approve, help="HUMAN ONLY: approve the current PLAN.md")
    p.add_argument("--by", nargs="+", required=True)
    p.add_argument("--secret", default=None, help="approval secret (or set OSR_APPROVAL_SECRET)")
    p = add("task-check", cmd_task_check, help="validate task cards")
    p.add_argument("task", nargs="?")
    p.add_argument("--all", action="store_true")
    p = add("start", cmd_start, help="begin a task attempt (gated)")
    p.add_argument("task")
    p.add_argument("--model", default=None, help="name of the model doing the implementation")
    p = add("check", cmd_check, help="scope + placeholder + reference checks")
    p.add_argument("task")
    p = add("verify", cmd_verify, help="run checks and verification commands; evidence goes to the ledger")
    p.add_argument("task")
    p = add("review", cmd_review, help="validate and record a review file")
    p.add_argument("task")
    p.add_argument("stage", choices=["spec", "quality"])
    p.add_argument("--reviewer", required=True, help="name of the model/person who reviewed")
    p = add("done", cmd_done, help="close a task if all gates pass")
    p.add_argument("task")
    p = add("triage", cmd_triage, help="diagnose a failed attempt (required before retry)")
    p.add_argument("task")
    p.add_argument("--layer", required=True, choices=LAYERS)
    p.add_argument("--evidence", required=True)
    p.add_argument("--change", required=True)
    p = add("unblock", cmd_unblock, help="HUMAN ONLY: clear a block or grant extra attempts")
    p.add_argument("task")
    p.add_argument("--by", nargs="+", required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--extra-attempts", type=int, default=0)
    p.add_argument("--secret", default=None, help="approval secret (or set OSR_APPROVAL_SECRET)")
    p = add("fixture-capture", cmd_fixture_capture, help="execute confirmed command to capture seam fixture")
    p.add_argument("path", help="destination path for captured fixture file")
    p.add_argument("--seam", required=True, help="seam id this fixture belongs to")
    p.add_argument("--cmd", required=True, help="confirmed command that outputs fixture payload to stdout")
    p = add("fixture-add", cmd_fixture_add, help="register a captured seam fixture")
    p.add_argument("path", help="path to fixture file")
    p.add_argument("--seam", required=True, help="seam id this fixture belongs to")
    p.add_argument("--source", required=True, help="source note of where fixture was captured")
    p = add("waive", cmd_waive, help="record a justified bypass of a check flag")
    p.add_argument("task")
    p.add_argument("flag_pos", nargs="?", default=None, help="check flag to waive (positional)")
    p.add_argument("--flag", default=None, help="check flag to waive")
    p.add_argument("--reason", required=True)
    p.add_argument("--approved-by", default=None)
    p.add_argument("--secret", default=None, help="approval secret (or set OSR_APPROVAL_SECRET)")
    p = add("signoff", cmd_signoff, help="HUMAN ONLY: sign off a manual or unverifiable requirement")
    p.add_argument("req")
    p.add_argument("--by", nargs="+", required=True)
    p.add_argument("--note", default="")
    p.add_argument("--secret", default=None, help="approval secret (or set OSR_APPROVAL_SECRET)")
    p = add("reset", cmd_reset, help="HUMAN ONLY: reset a task (e.g. after a plan change)")
    p.add_argument("task")
    p.add_argument("--by", nargs="+", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--secret", default=None, help="approval secret (or set OSR_APPROVAL_SECRET)")
    add("coverage", cmd_coverage, help="requirement to task to evidence matrix")
    p = add("audit", cmd_audit, help="final traceability audit (writes .ai/AUDIT.md)")
    p.add_argument("--check", action="store_true", help="read-only audit: same verdict, writes no project files")
    p.add_argument("--anchor", default=None, help="custom anchor file path to verify against")
    add("status", cmd_status, help="show state and write .ai/STATE.md")
    add("next", cmd_next, help="print the single next required action")
    p = add("anchor", cmd_anchor, help="record ledger head in an external anchor file (.osr-anchor)")
    p.add_argument("--out", default=None, help="custom anchor output file path (default: .osr-anchor)")
    p.add_argument("--file", default=None, help="alias for --out")
    p = add("ledger-verify", cmd_ledger_verify, help="check ledger integrity")
    p.add_argument("--anchor", default=None, help="custom anchor file path to verify against")
    p = add("review-pack", cmd_review_pack, help="bundle diff, task card, and criteria without builder rationale")
    p.add_argument("task")
    p.add_argument("--out", default=None, help="write pack to output file")
    p = add("quick", cmd_quick, help="rapid verification path without task card ceremony")
    p.add_argument("--verify", required=True, help="verification command to run")
    p.add_argument("--allowed", default=None, help="comma-separated list of allowed file patterns")

    global ROOT, JSON_MODE
    a = ap.parse_args()
    if a.root:
        ROOT = Path(a.root).resolve()
    if getattr(a, "json", False):
        JSON_MODE = True
    a.fn(a)


if __name__ == "__main__":
    main()
