# OSR v0.3.1 Implementation Extract

## Step 0: Outline (cheap map)

### Line Counts
- `scripts/osr.py`: 2475 | `integrations/antigravity/hooks.json`: 21 | `integrations/antigravity/pre_tool.py`: 107
- `integrations/antigravity/stop_hook.py`: 65 | `integrations/git/pre-commit`: 2 | `integrations/git/pre_commit.py`: 44
- `integrations/README.md`: 41 | `evals/eval_suite.py`: 791 | `evals/README.md`: 43 | `evals/__init__.py`: 1
- `tests/test_anchor_ext.py`: 133 | `tests/test_fixture_capture.py`: 208 | `tests/test_hardening_hypotheses.py`: 789
- `tests/test_honest_reporting.py`: 89 | `tests/test_osr.py`: 1591 | `tests/test_stop_hook.py`: 56
- `tests/test_tautological_ast.py`: 132 | `tests/test_zero_runner.py`: 132

### Function & Class Outline of `scripts/osr.py`
L93: is_mock_or_test_source | L132: scan_tautological_python | L198: scan_tautological_js | L225: ai | L229: now | L233: sha_text | L237: join_arg | L246: emit_json | L255: die | L266: class LedgerLock | L305: load_cfg | L314: save_cfg | L318: sha_config | L329: ensure_plan_and_config_approved | L336: check_approval_secret | L348: load_state | L357: save_state | L361: task_state | L372: class Ledger | L441: ctx | L453: glob_re | L474: matches | L478: count | L482: compiled | L488: file_info | L516: ignored | L520: walk_tree | L539: diff_tree | L552: fingerprint | L556: snap_path | L561: class Plan | L567: parse_plan | L651: task_ids | L659: parse_card | L679: is_verify_cmd_confirmed | L715: validate_card | L792: input_hash | L802: run_cmd | L812: tail | L817: save_log | L825: run_recorded | L841: confirmed | L854: pkg_deps | L872: js_resolves | L887: declared_python_dep | L898: py_resolves | L915: check_refs | L986: run_check | L1092: print_check | L1113: load_snap | L1120: require_active | L1127: require_not_failed_out | L1136: evidence_error | L1152: validate_spec_review | L1195: validate_quality_review | L1285: extract_passed_tests | L1315: gate_status | L1362: next_action | L1425: cmd_init | L1444: detect_commands | L1502: cmd_detect | L1520: cmd_confirm | L1533: cmd_env_check | L1545: cmd_plan_check | L1566: cmd_approve | L1594: cmd_task_check | L1619: cmd_start | L1684: cmd_check | L1694: cmd_verify | L1825: cmd_review | L1874: cmd_done | L1894: cmd_triage | L1921: cmd_unblock | L1933: cmd_waive | L1953: cmd_fixture_add | L1978: cmd_fixture_capture | L2023: cmd_signoff | L2036: cmd_reset | L2048: requirement_rows | L2088: cmd_coverage | L2097: cmd_audit | L2164: cmd_status | L2183: cmd_next | L2190: cmd_anchor | L2211: cmd_ledger_verify | L2220: cmd_review_pack | L2335: cmd_quick | L2367: main

### Test Files & Method Counts
`test_anchor_ext.py`: 2 | `test_fixture_capture.py`: 2 | `test_hardening_hypotheses.py`: 24 | `test_honest_reporting.py`: 2 | `test_osr.py`: 56 | `test_stop_hook.py`: 2 | `test_tautological_ast.py`: 4 | `test_zero_runner.py`: 3

---

## 1. Evidence classes

**PARTIAL**
Ledger entries store raw dicts without an explicit "observed/heuristic/attested" tag. In audit, status is derived as VERIFIED, HUMAN-SIGNED, or PENDING-HUMAN (UNVERIFIED).
```python
# file:scripts/osr.py:417-425
    def append(self, typ, task=None, attempt=None, **data):
        with LedgerLock(timeout=0.3):
            es = self.entries()
            prev = es[-1]["hash"] if es else ZERO
            body = {"seq": len(es) + 1, "ts": now(), "type": typ, "task": task, "attempt": attempt, "data": data, "prev": prev}
            body["hash"] = sha_text(prev + json.dumps(body, sort_keys=True))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(body) + "\n")
            return body
```
```python
# file:scripts/osr.py:1039-1040
    flags.append(("unanchored-mock:%s" % p, "test uses mock constructs on seam card without loading registered fixture (heuristic: flags common mock libraries)"))
```
```python
# file:scripts/osr.py:2151-2161
    bad = [r for r in rows if r[4] in ("UNCOVERED", "INCOMPLETE")] or notdone or not plan_ok
    pending = [r for r in rows if "PENDING-HUMAN" in r[4] or "UNVERIFIED" in r[4]]
    if seam_unverified:
        pending.append(("seams-conformance", "", "", "UNVERIFIED", ""))
    if bad:
        print("\nAUDIT: FAIL (gaps above)")
        sys.exit(1)
    if pending:
        print("\nAUDIT: COMPLETE WITH HUMAN REVIEW PENDING for: %s" % ", ".join(r[0] for r in pending))
        sys.exit(2)
```

---

## 2. Zero-test detection

**FOUND**
Matches runner stdout against known zero-test phrases in `run_recorded` and marks the command as suspect/failure. Covers pytest, unittest, and jest/vitest output styles.
```python
# file:scripts/osr.py:110-114
NO_TESTS = re.compile(
    r"(collected 0 items|no tests ran|no tests found|no test files|ran 0 tests|\b0 tests? (passed|run|found|executed)|"
    r"no tests to run|tests:\s+0 total|\b0 passing|test suites?:\s*0 total)",
    re.I,
)
```
```python
# file:scripts/osr.py:825-838
def run_recorded(cmd, cfg, label):
    code, text, secs, to = run_cmd(cmd, cfg)
    zero_tests = bool(NO_TESTS.search(text))
    suspect = zero_tests
    log = save_log(0, label, text)
    if not JSON_MODE:
        print("\n$ %s\n%s\n[exit %s%s | %ss | log .ai/logs/%s]" % (cmd, tail(text), code, " TIMEOUT" if to else "", secs, log))
        if zero_tests:
            print("SUSPECT: weak verify command: exit %s and output says no tests ran. Treated as FAILURE." % code)
    return {
        "cmd": cmd, "exit": code, "timeout": to, "suspect": suspect, "secs": secs,
        "output_sha": sha_text(text), "tail": tail(text, 15)[-1500:], "log": log,
        "ok": code == 0 and not suspect,
    }
```

---

## 3. Weak verify commands

**PARTIAL**
`TRIVIAL_CMD` and `WEAK_VERIFY_PAT` reject trivial commands and token existence checks in `validate_card`. Test selection flags (`-k`, `--grep`, `--testNamePattern`, `--lf`, `-x`, `--passWithNoTests`) are NOT checked.
```python
# file:scripts/osr.py:115-119
TRIVIAL_CMD = re.compile(r"^\s*(echo|true|exit\s+0|:|printf|print)\b", re.I)
WEAK_VERIFY_PAT = re.compile(
    r"(\bgrep\b|\bfindstr\b|\bSelect-String\b|-c\s+[\"'].*?(?:in\s+pathlib|sys\.exit|import\s+pathlib))",
    re.I,
)
```
```python
# file:scripts/osr.py:734-740
    for v in c["verify"]:
        if TRIVIAL_CMD.match(v):
            errs.append("%s: verify command '%s' cannot prove anything" % (tid, v))
        elif WEAK_VERIFY_PAT.search(v):
            errs.append("%s: verify command '%s' is a weak verify command (token existence check, not a test)" % (tid, v))
        elif not is_verify_cmd_confirmed(v, cfg):
            errs.append("%s: verify command '%s' is not confirmed (must match a confirmed command in .ai/config.json)" % (tid, v))
```

---

## 4. Tautology scanning

**PARTIAL**
Detects constant assertions and self-comparisons via Python AST and JS regexes. There is no check for test functions that contain zero assertions.
```python
# file:scripts/osr.py:166-189
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
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("assertEqual", "assertIs", "assert_equal") and len(node.args) >= 2:
                if same_node(node.args[0], node.args[1]):
                    findings.append((node.lineno, "Python AST: %s self-comparison" % name))
```
```python
# file:scripts/osr.py:125-129
JS_TAUTOLOGY_RE = [
    re.compile(r"expect\s*\(\s*([a-zA-Z0-9_$.]+)\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)"),
    re.compile(r"""expect\s*\(\s*(true|false|\d+|"[^"]*"|'[^']*')\s*\)\s*\.(toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)"""),
    re.compile(r"assert\s*\.\s*(equal|strictEqual|deepEqual)\s*\(\s*([a-zA-Z0-9_$.]+)\s*,\s*\2\s*\)"),
]
```

---

## 5. Mock detection

**FOUND**
Flags mock usage on tasks declaring seams if the test file does not reference a registered fixture. Evaluated only on changed files (`ch.items()`) for cards declaring `seams:`.
```python
# file:scripts/osr.py:1021-1041
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
                        anchored = any(fix and fix in content for fix in registered_fixtures)
                        if not anchored:
                            flags.append(("unanchored-mock:%s" % p, "test uses mock constructs on seam card without loading registered fixture (heuristic: flags common mock libraries)"))
```

---

## 6. Seam validation in `task-check`

**FOUND**
Checks that seam source is declared in `context_files` and rejects sources matching test/mock/fixture directory or file patterns.
```python
# file:scripts/osr.py:87-90
BOGUS_SOURCE_PAT = re.compile(
    r"(?:^|[/\\])(?:mocks?|fixtures?|stubs?|tests?|fakes?)(?:[/\\]|$)|(?:^|[/\\])(?:mock_|fake_|stub_|test_)[^/\\]+$|\.(?:mock|stub|fake|test|spec)\.[^/\\]+$",
    re.I,
)
```
```python
# file:scripts/osr.py:772-784
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
```

---

## 7. Fixtures

**PARTIAL**
`fixture-add` records path, seam, source note, sha256, date. `fixture-capture` records path, seam, confirmed cmd, sha256, date. Neither inspects network traffic or contacted endpoints.
```python
# file:scripts/osr.py:1964-1972
    st.setdefault("fixtures", {})
    st["fixtures"][rel_path] = {
        "sha256": h,
        "seam": a.seam,
        "source": a.source,
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_state(st)
    led.append("fixture_add", path=rel_path, seam=a.seam, source=a.source, sha256=h)
```
```python
# file:scripts/osr.py:2009-2018
    st.setdefault("fixtures", {})
    st["fixtures"][rel_path] = {
        "sha256": h,
        "seam": a.seam,
        "cmd": cmd,
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_state(st)
    led.append("fixture_capture", path=rel_path, seam=a.seam, cmd=cmd, sha256=h)
```

---

## 8. Conformance

**PARTIAL**
`conformance:` commands must be confirmed in `.ai/config.json`. The runner checks exit code 0 and non-zero test output, but does not check whether the command reads or references the seam source.
```python
# file:scripts/osr.py:741-749
    for v in c.get("conformance", []):
        if v in cfg.get("commands", {}):
            if not confirmed(cfg, None, v):
                errs.append("%s: conformance command '%s' is not confirmed (must run: osr confirm-commands)" % (tid, v))
        else:
            if TRIVIAL_CMD.match(v):
                errs.append("%s: conformance command '%s' cannot prove anything" % (tid, v))
            elif not is_verify_cmd_confirmed(v, cfg):
                errs.append("%s: conformance command '%s' is not confirmed (must match a confirmed command in .ai/config.json)" % (tid, v))
```
```python
# file:scripts/osr.py:2131-2148
    seam_unverified = []
    for t in ids:
        c = parse_card(t)
        if c.get("fixtures"):
            conf_entries = [e for e in led.entries() if e.get("task") == t and e.get("type") == "verify" and e.get("data", {}).get("ok")]
            has_conf = any(res.get("name") == "conformance" for ve in conf_entries for res in ve.get("data", {}).get("results", []))
            if not has_conf:
                seams_list = ", ".join(c.get("seams", [])) or "unnamed seam"
                seam_unverified.append("Task %s seam(s) '%s': declared fixtures %s without confirmed conformance run" % (
                    t, seams_list, ", ".join(c.get("fixtures", []))
                ))
```

---

## 9. Review citations

**FOUND**
Verifies snippet within 3 lines of cited line number. Requires cited path to match the seam authoritative source.
```python
# file:scripts/osr.py:1142-1149
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    if line < 1 or line > len(lines):
        return "evidence line %d is outside %s (%d lines)" % (line, path, len(lines))
    window = " ".join(lines[max(0, line - 4): line + 3])
    norm = lambda s: re.sub(r"\s+", " ", s).strip()
    if norm(snippet) not in norm(window):
        return "snippet not found within 3 lines of %s:%d (quote the real code)" % (path, line)
    return None
```
```python
# file:scripts/osr.py:1239-1246
    expected_source = plan_seams.get(sid, {}).get("source", "").strip()
    if Path(path).as_posix() != Path(expected_source).as_posix():
        errs.append("seam '%s': citation points to '%s', but authoritative source is '%s' (citations must point into the upstream source, not consumer files)" % (sid, path, expected_source))
    else:
        e = evidence_error(path, line_no, snippet)
        if e:
            errs.append("seam '%s': %s" % (sid, e))
```

---

## 10. Anchor

**PARTIAL**
Supports custom anchor file via `--out` or `--anchor` (default `.osr-anchor`). Verifies exact hash at sequence number. There is no warning if the anchor path is inside the repo or writable.
```python
# file:scripts/osr.py:2190-2205
def cmd_anchor(a):
    anchor_arg = getattr(a, "out", None) or getattr(a, "file", None)
    anchor_path = Path(anchor_arg).resolve() if anchor_arg else (ROOT / ".osr-anchor")
    led = Ledger()
    es = led.entries()
    if not es:
        die("Cannot anchor an empty ledger.", code=EXIT_USER_ERR)
    head = es[-1]
    data = {"seq": head["seq"], "head_hash": head["hash"], "hash": head["hash"], "ts": head.get("ts", now())}
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    anchor_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
```
```python
# file:scripts/osr.py:406-412
    if aseq is not None:
        if len(entries) < aseq or entries[aseq - 1]["hash"] != ahash:
            return False, "ledger anchor mismatch: rollback detected (expected seq %s with hash %s)" % (aseq, ahash)
    elif ahash:
        if not any(e["hash"] == ahash for e in entries):
            return False, "ledger anchor mismatch: anchored hash %s missing from ledger" % ahash
```

---

## 11. Human-only enforcement

**FOUND**
`check_approval_secret` verifies SHA-256 secret for `approve-plan`, `unblock`, `reset`, and `signoff`. Antigravity `pre_tool.py` blocks agent calls to these commands.
```python
# file:scripts/osr.py:336-346
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
```
```json
// file:integrations/antigravity/hooks.json:1-21
{
  "osr-enforcement": {
    "PreToolUse": [
      {
        "matcher": "edit_file|write_file|run_command",
        "hooks": [
          {
            "type": "command",
            "command": "python integrations/antigravity/pre_tool.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "python integrations/antigravity/stop_hook.py"
      }
    ]
  }
}
```
```python
# file:integrations/antigravity/pre_tool.py:47-60
    if name == "run_command":
        cmd = args.get("CommandLine", "")
        if re.search(r"\bosr\b", cmd, re.IGNORECASE) and re.search(r"\b(approve-plan|unblock|signoff|reset)\b", cmd, re.IGNORECASE):
            print(json.dumps({
                "decision": "deny",
                "reason": "Iron Rule 10: osr approve-plan/unblock/reset/signoff is human-only and blocked from agent execution."
            }))
            sys.exit(0)
        if re.search(r"OSR_APPROVAL_SECRET|\.osr-secret", cmd):
            print(json.dumps({"decision": "deny", "reason": "Access to approval secrets is blocked."}))
            sys.exit(0)
```

---

## 12. Stop hook

**PARTIAL**
`stop_hook.py` inspects `state.json` and blocks termination if tasks are not done. There is no loop guard or counter.
```python
# file:integrations/antigravity/stop_hook.py:34-51
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
                    "injectSteps": [{"ephemeralMessage": f"OSR Gate: workflow is not complete. Next required action: {next_act}"}]
                }))
                sys.exit(0)
```

---

## 13. Command confirmation

**PARTIAL**
`confirm-commands` records command string, exit code, output sha, and verified boolean. Config files (`package.json`, `pytest.ini`, `conftest.py`, etc.) are NOT fingerprinted.
```python
# file:scripts/osr.py:1524-1529
    for n, c in cfg["commands"].items():
        r = run_recorded(c["cmd"], cfg, "confirm-" + n)
        c["verified"] = r["ok"]
        led.append("cmd_confirm", name=n, cmd=c["cmd"], ok=r["ok"], exit=r["exit"], output_sha=r["output_sha"])
        print("=> %s: %s" % (n, "CONFIRMED" if r["ok"] else "NOT CONFIRMED (fix the command or the project, or remove it from config.json)"))
    save_cfg(cfg)
```

---

## 14. Red/green evidence

**FOUND**
Records baseline run outputs at `osr start` and compares them against post-implementation verify results to record transition states.
```python
# file:scripts/osr.py:1654-1663
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
```
```python
# file:scripts/osr.py:1778-1788
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
```

---

## 15. Undeclared boundary detection

**NOT FOUND**
Searched `scripts/osr.py` for checks scanning changed files for `fetch`, `axios`, `requests`, `http`, `WebSocket`, or URL literals on cards without seams. Only a keyword scan on `PLAN.md` exists in `cmd_plan_check` (L1551).

---

## 16. Suppression comments

**NOT FOUND**
Searched `scripts/osr.py` for checks scanning added `@ts-ignore`, `# type: ignore`, `eslint-disable`, `# noqa`, `as any`. No suppression comment checks exist.

---

## 17. `quick`

**FOUND**
Executes verify command directly with optional scope check. Skips plan checks, card validation, ledger hash-chain integrity, placeholder/shrink/secret checks, test weakening checks, tautology AST checks, unanchored mock checks, reviews, and audit.
```python
# file:scripts/osr.py:2335-2365
def cmd_quick(a):
    cfg, st, led = ctx(require_chain=False)
    if a.allowed:
        allowed_pats = [pt.strip() for pt in a.allowed.split(",") if pt.strip()]
        res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(ROOT))
        if res.returncode == 0:
            changed = [p[1].replace("\\", "/").strip('"\'') for l in res.stdout.splitlines() for p in [l.strip().split(maxsplit=1)] if len(p) == 2]
        else:
            cur = walk_tree(cfg)
            changed = [f for f in cur.keys() if not f.startswith(".ai/")]
        for f in changed:
            if not matches(f, allowed_pats):
                die("Scope violation: file '%s' is outside allowed files (%s)" % (f, a.allowed), code=EXIT_USER_ERR)
    res = run_recorded(a.verify, cfg, "quick")
    if not res["ok"]:
        sys.exit(2)
    led.append("quick_verify", cmd=a.verify, allowed=a.allowed, ok=True)
    print("QUICK VERIFY: PASS")
```

---

## 18. `review-pack`

**FOUND**
Bundles git diff, plan acceptance criteria, raw task card, declared seams table, and authoritative source files. Excludes builder notes, commit messages, and prior review files.
```python
# file:scripts/osr.py:2295-2315
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
```

---

## 19. Benchmark vectors V9 to V12

**FOUND**
Each vector has exactly 1 variant in `evals/eval_suite.py`.
```python
# file:evals/eval_suite.py:326-332 (V9)
    def test_format(self, mock_fetch):
        mock_fetch.return_value = {"id": 101, "name": "Alice"}
        self.assertEqual(calc.format_user(101), "Alice:101")
''')
        code, out = p.osr("verify", "T1")
        detected = (code != 0) and ("unanchored-mock" in out.lower() or "fixture" in out.lower() or "seam" in out.lower())
        return detected, "Self-confirming mock caught: " + ("yes" if detected else "no")
```
```python
# file:evals/eval_suite.py:377-380 (V10)
        p.write(".ai/tasks/T1.md", card)
        code, out = p.osr("task-check", "T1")
        detected = (code != 0) and ("missing from context_files" in out or "context_files" in out.lower())
        return detected, "Missing seam source in context_files caught: " + ("yes" if detected else "no")
```
```python
# file:evals/eval_suite.py:404-409 (V11)
        p.write("tests/test_calc.py", """import unittest
from src.calc import add
class CalcTest(unittest.TestCase):
    def test_add(self): self.assertEqual(1, 1)
""")
        code, out = p.osr("check", "T1")
        detected = (code != 0) and ("tautological" in out.lower() or "tests-weakened" in out.lower())
        return detected, "Tautological assertion caught: " + ("yes" if detected else "no (known miss in v0.2)")
```
```python
# file:evals/eval_suite.py:418-428 (V12)
        weak_cmd = f'"{sys.executable}" -c "import sys, pathlib; sys.exit(0 if \'def add\' in pathlib.Path(\'src/calc.py\').read_text() else 1)"'
        p.setup_ready(card_text=make_task_card(verify_cmd=weak_cmd))
        code, _ = p.osr("start", "T1")
        if code != 0:
            return True, "Start rejected weak verify command"
        p.write("src/calc.py", "def add(a, b):\n    return 'not_calculated'\n")
        p.write("tests/test_calc.py", CLEAN_TEST)
        code, out = p.osr("verify", "T1")
        detected = (code != 0) and ("weak" in out.lower() or "not a test" in out.lower())
        return detected, "Weak verify command caught: " + ("yes" if detected else "no (known miss in v0.2)")
```

---

## 20. Replay log

**NOT FOUND**
No raw log file of the Phase D replay exists under `.ai/logs/` or repository files (only summary markdown tables exist in `.ai/HARDENING-REPORT.md`).

---

## 21. README claims with no code

- `README.md:208`: "verified on Windows, Linux, and macOS across Python 3.8 through 3.12" — Python 3.10 and 3.11 are not executed in `.github/workflows/test.yml`.
- `README.md:58-62`: Antigravity Stop hook is claimed to block termination when incomplete, but `stop_hook.py` has no loop guard or attempt limit to prevent an infinite loop when human action is needed.

---

## Surprises

- `scripts/osr.py:2336`: `cmd_quick` invokes `ctx(require_chain=False)`, bypassing ledger cryptographic integrity verification.
- `scripts/osr.py:1551`: The keyword scanner for external boundaries only executes in `cmd_plan_check`, never in file check `run_check`.
- `integrations/antigravity/stop_hook.py:42`: The Stop hook emits both `"decision": "continue"` and `"terminationBehavior": "force_continue"`, which belongs to `PostInvocation`.
