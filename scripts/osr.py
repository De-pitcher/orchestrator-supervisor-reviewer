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
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

VERSION = "0.3.0"
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
                    ahash = ainfo.get("head_hash")
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


def is_verify_cmd_confirmed(v_cmd, cfg, led=None):
    if cfg.get("allow_no_commands"):
        return True
    if led is None:
        led = Ledger()
    conf_cmds = []
    for n, c in cfg.get("commands", {}).items():
        if confirmed(cfg, led, n):
            conf_cmds.append(c["cmd"].strip())
    if not conf_cmds:
        return True
    v_clean = v_cmd.strip()
    try:
        v_tokens = shlex.split(v_clean, posix=False)
    except Exception:
        v_tokens = v_clean.split()
    if not v_tokens:
        return False
    v_exe = v_tokens[0].strip('"\'>')
    for cc in conf_cmds:
        if v_clean == cc:
            return True
        try:
            c_tokens = shlex.split(cc, posix=False)
        except Exception:
            c_tokens = cc.split()
        if c_tokens:
            c_exe = c_tokens[0].strip('"\'>')
            if Path(v_exe).name.lower() == Path(c_exe).name.lower() or v_exe == c_exe:
                if len(c_tokens) > 2 and c_tokens[1] == "-m":
                    if len(v_tokens) > 2 and v_tokens[1] == "-m":
                        return v_tokens[2] == c_tokens[2]
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
    if led is None:
        led = Ledger()
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
                            flags.append(("unanchored-mock:%s" % p, "test uses mock constructs on seam card without loading registered fixture"))

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


def extract_passed_tests(text):
    passed = set()
    for m in re.finditer(r"^([a-zA-Z0-9_.:-]+)(?:\s*\([^)]*\))?\s*\.\.\.\s*ok\b", text, re.M):
        passed.add(m.group(1).split(".")[-1])
        passed.add(m.group(1))
    for m in re.finditer(r"::([a-zA-Z0-9_.:-]+)\s+PASSED", text):
        passed.add(m.group(1))
    for m in re.finditer(r"PASSED\s+\S*?::([a-zA-Z0-9_.:-]+)", text):
        passed.add(m.group(1))
    for m in re.finditer(r"^[ \t]*(?:✓|√)\s+([a-zA-Z0-9_.:-]+)", text, re.M):
        passed.add(m.group(1))
    for m in re.finditer(r'<testcase\s+[^>]*name=["\']([^"\']+)["\'][^>]*>(?!\s*<(?:failure|error|skipped))', text, re.I):
        passed.add(m.group(1))
    log_dir = ai("logs")
    if log_dir.exists():
        for log_xml in log_dir.glob("*.xml"):
            try:
                import xml.etree.ElementTree as ET
                tree = ET.parse(log_xml)
                for tc in tree.iter("testcase"):
                    if not list(tc.iter("failure")) and not list(tc.iter("error")) and not list(tc.iter("skipped")):
                        name = tc.get("name")
                        if name:
                            passed.add(name)
            except Exception:
                pass
    return sorted(passed)


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
        e_rev = led.latest("review", tid, a, stage)
        good = bool(e_rev and e_rev["data"].get("verdict") == "PASS" and fresh(e_rev))
        gates.append(("review-" + stage, good, "no passing, current %s review" % stage if not good else "ok"))

    plan, _ = parse_plan()
    if plan and e and fresh(e):
        passed_tests = set(e["data"].get("passed_tests", []))
        for r_id in card.get("requirements", []):
            req = plan.get(r_id, {})
            for ac in req.get("ac", []):
                m = re.search(r"\[([a-zA-Z0-9_.:-]+)\]", ac)
                if m:
                    test_id = m.group(1)
                    test_passed = any(test_id == pt or test_id in pt for pt in passed_tests)
                    gates.append((
                        "test-" + test_id,
                        test_passed,
                        "test '%s' mapped from %s did not run and pass" % (test_id, r_id) if not test_passed else "ok"
                    ))
        for neg in card.get("negative_tests", []):
            neg_passed = any(neg == pt or neg in pt for pt in passed_tests)
            gates.append((
                "negative-test-" + neg,
                neg_passed,
                "named negative test '%s' did not run and pass in recorded test output" % neg if not neg_passed else "ok"
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
    warnings = []
    if plan:
        seams = getattr(plan, "seams", {})
        if not seams:
            external_kw = re.compile(r"\b(api|service|endpoint|queue|socket|websocket|grpc|rpc|http|rest)\b", re.I)
            for r, v in plan.items():
                text_to_check = v["text"] + " " + " ".join(v.get("ac", []))
                m = external_kw.search(text_to_check)
                if m:
                    warnings.append("PLAN WARNING: requirement %s mentions external interface ('%s') but Seams table is empty (consider declaring in ## Seams)" % (r, m.group(1)))
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
    h = sha_text(ai("PLAN.md").read_text(encoding="utf-8"))
    st["plan_hash"] = h
    cfg_h = sha_config()
    st["config_hash"] = cfg_h
    save_state(st)
    by_val = join_arg(a.by)
    led.append("plan_approved", by=by_val, plan_hash=h, config_hash=cfg_h)
    print("Plan approved by %s. Any later edit to PLAN.md or config.json voids approval until re-approved." % by_val)


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
    ensure_plan_and_config_approved(st)
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
    baseline = {}
    for n in cfg.get("global_verify", []):
        if n in cfg.get("commands", {}) and confirmed(cfg, led, n):
            res = run_recorded(cfg["commands"][n]["cmd"], cfg, "%s-baseline-%s" % (tid, n))
            baseline[n] = {"ok": res["ok"], "exit": res["exit"], "sha": res["output_sha"]}
    for i, v in enumerate(card["verify"]):
        if not TRIVIAL_CMD.match(v) and is_verify_cmd_confirmed(v, cfg, led):
            res = run_recorded(v, cfg, "%s-baseline-task-%d" % (tid, i))
            baseline["task_%d" % i] = {"cmd": v, "ok": res["ok"], "exit": res["exit"], "sha": res["output_sha"]}

    with LedgerLock(timeout=0.3):
        if not snap_path(tid).exists():
            snap_path(tid).write_text(json.dumps(cur), encoding="utf-8")
        ts.update({"status": "in_progress", "attempts": ts["attempts"] + 1, "failures": 0, "model": a.model or "unknown", "input_hash": ih, "requires": None, "baseline": baseline})
        save_state(st)
        led.append("start", tid, ts["attempts"], model=ts["model"], input_hash=ih, baseline=baseline)
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
    for res in results:
        if res.get("log"):
            log_p = ai("logs", res["log"])
            if log_p.exists():
                all_output_text += "\n" + log_p.read_text(encoding="utf-8", errors="replace")
    passed_tests = extract_passed_tests(all_output_text)
    if card.get("negative_tests"):
        missing_neg = [t for t in card["negative_tests"] if not any(t == pt or t in pt for pt in passed_tests)]
        if missing_neg:
            print("WARNING: named negative test(s) not found in test output: %s" % ", ".join(missing_neg))
        else:
            print("Negative tests verified: %s" % ", ".join(card["negative_tests"]))
    clean_results = [{k: v for k, v in x.items() if k != "tail"} for x in results]
    led.append("verify", tid, ts["attempts"], ok=ok, fp=r2["fp"], results=clean_results, red_green=red_green, passed_tests=passed_tests)
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


def requirement_rows(cfg, st, led, plan):
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
            else:
                statuses = []
                for t in tasks:
                    e = led.latest("review", t, task_state(st, t)["attempts"], "spec")
                    if e:
                        statuses.append((e["data"].get("items") or {}).get(r, {}))
                if any(s.get("status") == "PASS" for s in statuses) and v["check"] == "auto":
                    status = "VERIFIED"
                    ev = next(s["evidence"] for s in statuses if s.get("status") == "PASS")
                    test_tags = []
                    for ac in v.get("ac", []):
                        m = re.search(r"\[([a-zA-Z0-9_.:-]+)\]", ac)
                        if m:
                            test_tags.append(m.group(1))
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
    pending = [r for r in rows if "PENDING-HUMAN" in r[4] or "UNVERIFIED" in r[4]]
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
    anchor_path = Path(a.file).resolve() if getattr(a, "file", None) else (ROOT / ".osr-anchor")
    led = Ledger()
    es = led.entries()
    if not es:
        die("Cannot anchor an empty ledger.", code=EXIT_USER_ERR)
    head = es[-1]
    data = {
        "seq": head["seq"],
        "head_hash": head["hash"],
        "ts": head.get("ts", now()),
    }
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
    cfg, st, led = ctx(require_chain=False)
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

    res = run_recorded(a.verify, cfg, "quick")
    if not res["ok"]:
        if JSON_MODE:
            emit_json({"ok": False, "exit_code": 2, "status": "gate_failed", "cmd": a.verify, "log": res.get("log")}, code=2)
        print("QUICK VERIFY: FAIL")
        sys.exit(2)

    led.append("quick_verify", cmd=a.verify, allowed=a.allowed, ok=True)
    if JSON_MODE:
        emit_json({"ok": True, "exit_code": 0, "status": "ok", "cmd": a.verify, "allowed": a.allowed}, code=0)
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
    add("audit", cmd_audit, help="final traceability audit (writes .ai/AUDIT.md)")
    add("status", cmd_status, help="show state and write .ai/STATE.md")
    add("next", cmd_next, help="print the single next required action")
    p = add("anchor", cmd_anchor, help="record ledger head in an external anchor file (.osr-anchor)")
    p.add_argument("--file", default=None, help="custom anchor file path (default: .osr-anchor)")
    p = add("ledger-verify", cmd_ledger_verify, help="check ledger integrity")
    p.add_argument("--anchor", default=None, help="custom anchor file path to verify against")
    p = add("review-pack", cmd_review_pack, help="bundle diff, task card, and criteria without builder rationale")
    p.add_argument("task")
    p.add_argument("--out", default=None, help="write pack to output file")
    p = add("quick", cmd_quick, help="rapid verification path without task card ceremony")
    p.add_argument("--verify", required=True, help="verification command to run")
    p.add_argument("--allowed", default=None, help="comma-separated list of allowed file patterns")

    a = ap.parse_args()
    if a.root:
        ROOT = Path(a.root).resolve()
    if getattr(a, "json", False):
        JSON_MODE = True
    a.fn(a)


if __name__ == "__main__":
    main()
