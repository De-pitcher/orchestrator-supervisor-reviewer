# Phase 0 Reconciliation Report: v0.3.1 Claims vs. Reality

Date: 2026-10-22  
Branch: `v0.3.2` (branched from `v0.3.1-hardening`)  
Commit: `769b3071486b91315b4529e9749152b3e7ac7559`

---

## 1. Git Environment & History

- **Current Branch**: `v0.3.2`
- **Base Commit**: `769b3071486b91315b4529e9749152b3e7ac7559`
- **Recent Commit Log (`git log --oneline -8`)**:
  ```text
  769b307 feat(harden): osr v0.3.1 hardening - hook contract, fixture capture, AST checks, runner validation, out-of-band anchors
  1aebc78 docs(audit): final audit report and state synchronization for v0.3.0
  5ffd41e feat(osr): phase 6 benchmark expansion, multi-fixture reporting, and release v0.3.0 (T6)
  7c05f90 feat(osr): phase 5 adversarial review pack and manual audit signoff (T5)
  b81225d feat(osr): Phase 4 - conditional kinds (realtime appendix) and per-seam negative tests
  346b041 feat(osr): Phase 3 - fixtures, conformance, and unanchored-mock defense (V9 caught)
  9fdf7a2 feat(reviews): implement Phase 2 seam citations in quality reviews
  ca47df6 feat(seams): implement Phase 1 seam inventory (plan and card level)
  ```

---

## 2. Claims vs. Reality Reconciliation Table

| # | Item / Area | Claim in v0.3.1 Dossier & Reports | Reality on Branch `v0.3.2` | Mechanical Evidence | Status |
|---|---|---|---|---|---|
| 1 | **Stop Hook Output Contract** | Dossier claimed `stop_hook.py` was refactored to inspect `osr status --json` and emit official schema `{"decision": "block", "reason": "..."}`. | The hook emits `decision: continue`, retains invalid fields `terminationBehavior: force_continue` and `injectSteps`, reads raw `state.json`, and has no loop guard. | `git diff v0.3.0 -- integrations/antigravity/stop_hook.py` shows only `"decision": "continue"` and `"decision": "approve"` were added alongside legacy `terminationBehavior`. Lines 28-34 directly read `.ai/state.json`. | **DISCREPANCY (CONTRADICTION)** |
| 2 | **Stop Hook Loop Guard** | Claimed to stop agent from infinite loops when human intervention is required. | No loop guard counter, attempt limit, or active check exists. Hook continues indefinitely as long as tasks are incomplete. | `integrations/antigravity/stop_hook.py:34-51` unconditionally returns `continue` whenever `any(tinfo.get("status") == "in_progress"...)`. | **DISCREPANCY (MISSING)** |
| 3 | **Test Discovery Count & Status** | Dossier claimed 66 unit tests passing with 0 failures and 0 errors. External count showed ~95 test methods. | Exactly 66 `TestCase` methods are discovered by unittest. The ~95 count came from grep matching nested `def test_...` in string fixtures inside test methods. However, **3 tests currently fail** due to hardcoded v0.3.0 assertions. | `python -m unittest discover -s tests` reports: `Ran 66 tests in 325.273s FAILED (failures=3)`: (1) `test_adversarial_eval_suite_benchmarks_catch_rate` (expected 10 caught, got 12), (2) `test_phase6_benchmark_and_honest_reporting` (expected version '0.3.0', got '0.3.1'), (3) `test_phase6_version_and_docs_integrity` (expected VERSION '0.3.0', got '0.3.1'). | **DISCREPANCY (3 FAILING TESTS)** |
| 4 | **CI Matrix vs. README Claims** | README claims "verified on Windows, Linux, and macOS across Python 3.8 through 3.12". | `.github/workflows/test.yml` line 9 was updated to `["3.8", "3.9", "3.10", "3.11", "3.12"]` in commit `769b307`, but no green GitHub Actions run has executed or been linked yet for Python 3.8, 3.10, or 3.11. | `git show v0.3.0:.github/workflows/test.yml` showed only `["3.9", "3.12"]`. Commit `769b307` added the missing versions, but remote CI run verification remains pending. | **PARTIAL / PENDING CI VERIFICATION** |
| 5 | **Global Skill Synchronization** | Dossier claimed all files synchronized to `~/.gemini/config/skills/orchestrator-supervisor-reviewer`. | Core CLI, docs, and integrations were copied, but `tests/` in the global skill directory was NOT fully synchronized (only has stale `test_osr.py`, missing all 7 new test files). | File comparison between repo and `~/.gemini/config/skills/orchestrator-supervisor-reviewer` showed `tests/test_anchor_ext.py`, `tests/test_fixture_capture.py`, `tests/test_hardening_hypotheses.py`, `tests/test_honest_reporting.py`, `tests/test_stop_hook.py`, `tests/test_tautological_ast.py`, `tests/test_zero_runner.py` are missing in skill copy. | **DISCREPANCY (INCOMPLETE SYNC)** |
| 6 | **Evidence Classes in Ledger** | Dossier suggested structured distinction between observed, heuristic, and attested evidence. | Ledger schema body contains only `{"seq", "ts", "type", "task", "attempt", "data", "prev", "hash"}`. No `evidence` class field exists. | `scripts/osr.py:421`: `body = {"seq": len(es) + 1, "ts": now(), "type": typ, "task": task, "attempt": attempt, "data": data, "prev": prev}`. | **DISCREPANCY (UNIMPLEMENTED)** |
| 7 | **Approval Secret Mechanism** | Claimed human-only commands are strictly gated by secret. | Secret is optional, unsalted SHA-256 in `config.json`, and can be supplied via `--secret` or `OSR_APPROVAL_SECRET` env var (both readable by agent in memory/process table). | `scripts/osr.py:336-346`: `provided = getattr(a, "secret", None) or os.environ.get("OSR_APPROVAL_SECRET")`, compared against `cfg.get("approval_secret_sha")`. | **DISCREPANCY (WEAK SECURITY)** |
| 8 | **`quick` Command Integrity** | Dossier claimed `quick` path verifies scope and tests directly. | `quick` explicitly bypasses ledger chain integrity (`ctx(require_chain=False)`), skips command confirmation, skips weak command patterns, and skips card/review gates. | `scripts/osr.py:2336`: `cfg, st, led = ctx(require_chain=False)`. No check against `TRIVIAL_CMD` or `WEAK_VERIFY_PAT`. | **DISCREPANCY (CONFIRMED BYPASS)** |

---

## 3. Discrepancy Breakdown & Root Causes

1. **Stop Hook Contract Mismatch**:
   - `integrations/antigravity/stop_hook.py` was adjusted to output `"decision": "continue"` instead of `"terminationBehavior"` alone, but retained `"terminationBehavior": "force_continue"` and `"injectSteps"`, and continued reading `.ai/state.json` directly.
   - It completely lacks a loop guard counter or check for human-pending actions (`approve-plan`, `signoff`, `unblock`).
2. **Three Failing Unit Tests in Test Suite**:
   - When v0.3.1 bumped `VERSION = "0.3.1"` and `evals/eval_suite.py` caught 12 vectors instead of 10, three tests in `tests/test_osr.py` (lines 596, 1542, 1561) failed because their test assertions hardcoded `"0.3.0"` and 10 caught vectors.
3. **Test Discovery Denominator Discrepancy (66 vs ~95)**:
   - The test runner actually loads and runs **66 test cases**.
   - Naive grepping for `def test_` matched 29 internal functions defined inside multiline strings within test files (e.g., test fixtures generated dynamically for test runs in `test_tautological_ast.py` and `test_hardening_hypotheses.py`).
4. **Stale Tests in Skill Copy**:
   - The local skill directory received `scripts/osr.py`, `SKILL.md`, and docs, but `Copy-Item` did not overwrite the entire `tests/` folder, leaving the global skill test suite in a mixed, stale state.
