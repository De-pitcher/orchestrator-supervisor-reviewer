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
from pathlib import Path

VERSION = "0.1.0"
ROOT = Path.cwd()
SCRIPT_DIR = Path(__file__).resolve().parent
ASSETS = SCRIPT_DIR.parent / "assets"
ZERO = "0" * 64
LAYERS = ["spec", "plan", "prompt", "context", "environment", "model", "implementation"]

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
    "human_only_flags": ["tests-weakened", "skips-added", "secret"],
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
CODE_EXTS = {
    ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".scala", ".dart", ".ex", ".exs", ".lua", ".sh", ".ps1", ".vue", ".svelte", ".r", ".jl", ".zig",
}
JS_EXTS = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]
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


def load_state():
    p = ai("state.json")
    if not p.exists():
        return {"plan_hash": None, "tasks": {}, "waivers": [], "signoffs": {}}
    return json.loads(p.read_text(encoding="utf-8"))


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

    def verify_chain(self):
        prev = ZERO
        for i, e in enumerate(self.entries()):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev") != prev:
                return False, "ledger entry %d: broken chain" % (i + 1)
            if sha_text(prev + json.dumps(body, sort_keys=True)) != e.get("hash"):
                return False, "ledger entry %d: content was modified" % (i + 1)
            prev = e["hash"]
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


# ----------------------------------------------------------------------------- plan and cards
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
        m = re.match(r"^\s*[-*]\s*(R\d+)\s*:\s*(.+)$", ln)
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
    if not reqs:
        errs.append("PLAN.md: no requirements found (format: '- R1: text' then indented '- AC:' and '- Check: auto|manual')")
    for r, v in reqs.items():
        if not v["ac"]:
            errs.append("PLAN.md: %s has no '- AC:' acceptance criterion" % r)
        elif any(len(a) < 15 for a in v["ac"]):
            errs.append("PLAN.md: %s has an acceptance criterion shorter than 15 chars (be concrete and testable)" % r)
        if v["check"] not in ("auto", "manual"):
            errs.append("PLAN.md: %s needs '- Check: auto' or '- Check: manual'" % r)
    for key, lines in sections.items():
        if "open question" in key or "assumption" in key:
            for ln in lines:
                if re.match(r"^\s*[-*]\s*\[ \]", ln):
                    errs.append("PLAN.md: unresolved item under '%s': %s (resolve it with the human, then tick [x])" % (key, ln.strip()))
    return reqs, errs


CARD_KEYS = ["id", "requirements", "depends_on", "allowed_files", "forbidden_files", "context_files", "verify"]
CARD_LIST_KEYS = ["requirements", "depends_on", "allowed_files", "forbidden_files", "context_files"]
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


def save_log(led_seq_hint, label, text):
    d = ai("logs")
    d.mkdir(parents=True, exist_ok=True)
    name = "%s-%s.log" % (time.strftime("%Y%m%d-%H%M%S"), re.sub(r"[^A-Za-z0-9_-]", "_", label))
    (d / name).write_text(text, encoding="utf-8")
    return name


def run_recorded(cmd, cfg, label):
    code, text, secs, to = run_cmd(cmd, cfg)
    suspect = bool(NO_TESTS.search(text)) and code == 0
    log = save_log(0, label, text)
    if not JSON_MODE:
        print("\n$ %s\n%s\n[exit %s%s | %ss | log .ai/logs/%s]" % (cmd, tail(text), code, " TIMEOUT" if to else "", secs, log))
        if suspect:
            print("SUSPECT: exit 0 but output says no tests ran. Treated as FAILURE.")
    return {
        "cmd": cmd, "exit": code, "timeout": to, "suspect": suspect, "secs": secs,
        "output_sha": sha_text(text), "tail": tail(text, 15)[-1500:], "log": log,
        "ok": code == 0 and not suspect,
    }


def confirmed(cfg, led, name):
    c = cfg["commands"].get(name)
    if not c or not c.get("verified"):
        return False
    for e in reversed(led.entries()):
        if e["type"] == "cmd_confirm" and e["data"].get("name") == name and e["data"].get("cmd") == c["cmd"]:
            return bool(e["data"].get("ok"))
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
    waived = {w["flag"] for w in st["waivers"] if w["task"] == tid}
    unwaived = [(f, m) for f, m in flags if f not in waived]
    refs = check_refs(ch)
    ok = not viol and not unwaived and not refs["unresolved"] and not refs["syntax"]
    return {
        "ok": ok, "fp": fp, "changed": ch, "violations": viol, "flags": [f for f, _ in flags],
        "unwaived": unwaived, "waived": sorted(f for f, _ in flags if f in waived), "refs": refs,
    }


def print_check(r):
    print("Changed files: %d" % len(r["changed"]))
    for p, s in sorted(r["changed"].items()):
        print("  %s %s" % (s, p))
    for v in r["violations"]:
        print("SCOPE VIOLATION: %s" % v)
    for f, m in r["unwaived"]:
        print("FLAG: %s  (%s)\n  waive only with a real reason: osr waive <task> --flag \"%s\" --reason \"...\"" % (f, m, f))
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


def validate_quality_review(text):
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
    declared = re.search(r"^\s*VERDICT:\s*(PASS|FAIL)\b", text, re.M)
    derived = "FAIL" if any(v == "FAIL" for v in items.values()) else "PASS"
    if not declared:
        errs.append("missing final line  VERDICT: PASS|FAIL")
    elif declared.group(1) != derived:
        errs.append("VERDICT says %s but the checklist implies %s" % (declared.group(1), derived))
    return errs, items, derived


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
    gates = []

    def fresh(e):
        return e is not None and e["data"].get("fp") == fp

    e = led.latest("verify", tid, a)
    gates.append(("verify", bool(e and e["data"].get("ok") and fresh(e)),
                  "no passing verify for the current code" if not e or not fresh(e) or not e["data"].get("ok") else "ok"))
    for stage in ("spec", "quality"):
        e = led.latest("review", tid, a, stage)
        good = bool(e and e["data"].get("verdict") == "PASS" and fresh(e))
        gates.append(("review-" + stage, good, "no passing, current %s review" % stage if not good else "ok"))
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
        led.append("cmd_confirm", name=n, cmd=c["cmd"], ok=r["ok"], exit=r["exit"], output_sha=r["output_sha"])
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
    for e in errs:
        print("PLAN ERROR: " + e)
    if not errs:
        print("PLAN OK: %d requirements (%d manual)" % (len(plan), sum(1 for v in plan.values() if v["check"] == "manual")))
    sys.exit(1 if errs else 0)


def cmd_approve(a):
    cfg, st, led = ctx()
    plan, errs = parse_plan()
    if errs:
        die("Plan invalid:\n  " + "\n  ".join(errs))
    if not any(confirmed(cfg, led, n) for n in cfg["commands"]) and not cfg["allow_no_commands"]:
        die("No confirmed verification command. Run detect + confirm-commands (or set allow_no_commands for a brand-new project).")
    h = sha_text(ai("PLAN.md").read_text(encoding="utf-8"))
    st["plan_hash"] = h
    save_state(st)
    by_val = join_arg(a.by)
    led.append("plan_approved", by=by_val, plan_hash=h)
    print("Plan approved by %s. Any later edit to PLAN.md voids approval until re-approved." % by_val)


def cmd_task_check(a):
    cfg, st, led = ctx()
    plan, perrs = parse_plan()
    ids = task_ids() if a.all or not a.task else [a.task]
    allerrs = []
    for t in ids:
        c, e = validate_card(t, cfg, plan)
        allerrs += e
        print("%s: %s" % (t, "OK" if not e else "INVALID"))
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
    if st["plan_hash"] != sha_text(ai("PLAN.md").read_text(encoding="utf-8")):
        die("PLAN.md is not approved or changed since approval. The human must run: osr approve-plan --by <name>")
    card, errs = validate_card(tid, cfg, plan)
    if errs:
        die("Task card invalid:\n  " + "\n  ".join(errs))
    ts = task_state(st, tid)
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
    with LedgerLock(timeout=0.3):
        if not snap_path(tid).exists():
            snap_path(tid).write_text(json.dumps(cur), encoding="utf-8")
        ts.update({"status": "in_progress", "attempts": ts["attempts"] + 1, "failures": 0, "model": a.model or "unknown", "input_hash": ih, "requires": None})
        save_state(st)
        led.append("start", tid, ts["attempts"], model=ts["model"], input_hash=ih)
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
    tid = a.task
    ts = require_active(st, tid)
    require_not_failed_out(cfg, ts, tid)
    card, errs = validate_card(tid, cfg, parse_plan()[0])
    if errs:
        die("Task card invalid:\n  " + "\n  ".join(errs))
    snap = load_snap(tid)
    r = run_check(cfg, st, tid, card, snap, walk_tree(cfg))
    if not JSON_MODE:
        print_check(r)
    led.append("check", tid, ts["attempts"], ok=r["ok"], fp=r["fp"], flags=r["flags"], unchecked=r["refs"]["unchecked"][:30])
    if not r["ok"]:
        ts["failures"] += 1
        save_state(st)
        led.append("verify", tid, ts["attempts"], ok=False, fp=r["fp"], reason="pre-check failed", results=[])
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
    cmds += [("task", v) for v in card["verify"]]
    results, ok = [], True
    for n, cmd in cmds:
        res = run_recorded(cmd, cfg, "%s-%s" % (tid, n))
        res["name"] = n
        results.append(res)
        ok = ok and res["ok"]
    cur2 = walk_tree(cfg)
    r2 = run_check(cfg, st, tid, card, snap, cur2)
    if not r2["ok"] and r["ok"]:
        if not JSON_MODE:
            print("The verification run itself changed files outside scope or created flagged content:")
            print_check(r2)
        ok = False
    led.append("check", tid, ts["attempts"], ok=r2["ok"], fp=r2["fp"], flags=r2["flags"], unchecked=r2["refs"]["unchecked"][:30])
    clean_results = [{k: v for k, v in x.items() if k != "tail"} for x in results]
    led.append("verify", tid, ts["attempts"], ok=ok, fp=r2["fp"], results=clean_results)
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
            "next": next_action()
        }, code=0 if ok else 2)
    print("\nVERIFY: %s" % ("PASS" if ok else "FAIL  (failures this attempt: %d/%d)" % (ts["failures"], cfg["max_inner_failures"])))
    print("NEXT: %s" % next_action())
    sys.exit(0 if ok else 2)


def cmd_review(a):
    cfg, st, led = ctx()
    tid, stage = a.task, a.stage
    ts = require_active(st, tid)
    require_not_failed_out(cfg, ts, tid)
    card, errs = validate_card(tid, cfg, parse_plan()[0])
    snap = load_snap(tid)
    cur = walk_tree(cfg)
    fp = fingerprint(diff_tree(snap, cur), cur)
    v = led.latest("verify", tid, ts["attempts"])
    if not v or not v["data"].get("ok") or v["data"].get("fp") != fp:
        die("No passing verify for the CURRENT code. Reviews only apply to verified code. Run: osr verify %s" % tid)
    if stage == "quality":
        s = led.latest("review", tid, ts["attempts"], "spec")
        if not s or s["data"].get("verdict") != "PASS" or s["data"].get("fp") != fp:
            die("Spec review must pass (for the current code) before the quality review.")
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
        errs, items, verdict = validate_quality_review(text)
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
    led.append("review", tid, ts["attempts"], stage=stage, verdict=verdict, fp=fp, file_sha=fsha, reviewer=a.reviewer, self_review=self_review, items=items)
    if verdict == "FAIL":
        ts["failures"] += 1
        save_state(st)
        print("REVIEW RECORDED: FAIL (failures this attempt: %d/%d). Fix the code, then osr verify %s and re-review." % (ts["failures"], cfg["max_inner_failures"], tid))
        sys.exit(1)
    print("REVIEW RECORDED: %s PASS" % stage)
    print("NEXT: %s" % next_action())


def cmd_done(a):
    cfg, st, led = ctx()
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
    ts["status"] = "done"
    save_state(st)
    led.append("done", tid, ts["attempts"], fp=fp)
    print("Task %s DONE (attempt %d)." % (tid, ts["attempts"]))
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
    ts = task_state(st, a.task)
    ts["blocked"] = None
    ts["extra_attempts"] += a.extra_attempts
    save_state(st)
    by_val = join_arg(a.by)
    led.append("unblock", a.task, ts["attempts"], by=by_val, note=a.note, extra_attempts=a.extra_attempts)
    print("Unblocked %s by %s." % (a.task, by_val))


def cmd_waive(a):
    cfg, st, led = ctx()
    ts = task_state(st, a.task)
    if len(a.reason) < 15:
        die("A waiver needs a real reason (15+ chars).")
    kind = a.flag.split(":")[0]
    if kind in cfg["human_only_flags"] and not a.approved_by:
        die("'%s' flags need human approval. Ask the human, then add: --approved-by <name>" % kind)
    st["waivers"].append({"task": a.task, "flag": a.flag, "reason": a.reason, "approved_by": a.approved_by})
    save_state(st)
    led.append("waive", a.task, ts["attempts"], flag=a.flag, reason=a.reason, approved_by=a.approved_by)
    print("Waiver recorded (visible in the final audit).")


def cmd_signoff(a):
    cfg, st, led = ctx()
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
    st["tasks"][a.task] = task_state({"tasks": {}}, a.task)
    if snap_path(a.task).exists():
        snap_path(a.task).unlink()
    save_state(st)
    by_val = join_arg(a.by)
    led.append("reset", a.task, None, by=by_val, reason=a.reason)
    print("Task %s reset (history stays in the ledger)." % a.task)


def requirement_rows(cfg, st, led, plan):
    rows = []
    ids = task_ids()
    cards = {t: parse_card(t) for t in ids}
    for r, v in plan.items():
        tasks = [t for t in ids if r in cards[t]["requirements"]]
        status, ev = "UNCOVERED", ""
        if tasks:
            if any(task_state(st, t)["status"] != "done" for t in tasks):
                status = "INCOMPLETE"
            else:
                statuses = []
                for t in tasks:
                    e = led.latest("review", t, task_state(st, t)["attempts"], "spec")
                    if e:
                        statuses.append((e["data"].get("items") or {}).get(r, {}))
                if any(s.get("status") == "PASS" for s in statuses) and v["check"] == "auto":
                    status = "VERIFIED"
                    ev = next(s["evidence"] for s in statuses if s.get("status") == "PASS")
                elif r in st["signoffs"]:
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
    plan, errs = parse_plan()
    if errs:
        die("Plan invalid:\n  " + "\n  ".join(errs))
    rows = requirement_rows(cfg, st, led, plan)
    ids = task_ids()
    notdone = [t for t in ids if task_state(st, t)["status"] != "done"]
    plan_ok = st["plan_hash"] == sha_text(ai("PLAN.md").read_text(encoding="utf-8"))
    lines = ["# Audit  (%s)" % now(), "", "Ledger integrity: ok. Plan approved and unchanged: %s." % plan_ok, "", "## Requirement traceability", "",
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
    ai("AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    bad = [r for r in rows if r[4] in ("UNCOVERED", "INCOMPLETE")] or notdone or not plan_ok
    pending = [r for r in rows if r[4] == "PENDING-HUMAN"]
    if bad:
        print("\nAUDIT: FAIL (gaps above)")
        sys.exit(1)
    if pending:
        print("\nAUDIT: COMPLETE WITH HUMAN REVIEW PENDING for: %s" % ", ".join(r[0] for r in pending))
        sys.exit(2)
    print("\nAUDIT: PASS (every requirement has machine evidence or human sign-off)")


def cmd_status(a):
    cfg, st, led = ctx()
    ok, msg = led.verify_chain()
    lines = ["# State", "", "Ledger: %s" % msg, ""]
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


def cmd_ledger_verify(a):
    ok, msg = Ledger().verify_chain()
    if JSON_MODE:
        emit_json({"ok": ok, "exit_code": 0 if ok else 4, "status": "ok" if ok else "integrity_violation", "message": msg}, code=0 if ok else 4)
    print("LEDGER: %s" % msg)
    sys.exit(0 if ok else 4)


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
    p = add("waive", cmd_waive, help="record a justified bypass of a check flag")
    p.add_argument("task")
    p.add_argument("--flag", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--approved-by", default=None)
    p = add("signoff", cmd_signoff, help="HUMAN ONLY: sign off a manual or unverifiable requirement")
    p.add_argument("req")
    p.add_argument("--by", nargs="+", required=True)
    p.add_argument("--note", default="")
    p = add("reset", cmd_reset, help="HUMAN ONLY: reset a task (e.g. after a plan change)")
    p.add_argument("task")
    p.add_argument("--by", nargs="+", required=True)
    p.add_argument("--reason", required=True)
    add("coverage", cmd_coverage, help="requirement to task to evidence matrix")
    add("audit", cmd_audit, help="final traceability audit (writes .ai/AUDIT.md)")
    add("status", cmd_status, help="show state and write .ai/STATE.md")
    add("next", cmd_next, help="print the single next required action")
    add("ledger-verify", cmd_ledger_verify, help="check ledger integrity")

    a = ap.parse_args()
    if a.root:
        ROOT = Path(a.root).resolve()
    if getattr(a, "json", False):
        JSON_MODE = True
    a.fn(a)


if __name__ == "__main__":
    main()
