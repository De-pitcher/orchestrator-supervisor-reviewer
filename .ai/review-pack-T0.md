# Review Pack: T0

> **Adversarial Review Directive**:
> For every external field, find its definition in the provided source. Report any field the code uses that the source does not declare. Do not trust the builder's explanation.

## Acceptance Criteria
- **R0**: 
  - AC: Fix the 3 failing tests in tests/test_osr.py by asserting version consistency across the project (osr.VERSION == pyproject version == eval_suite version == top CHANGELOG entry) and asserting benchmark results per required vector ID without hardcoded counts and without weakening (no test removed, assertion counts not reduced) [test_baseline_repair_green]
  - AC: Execute a confirmed global_verify command validating the full test suite is green with pass count recorded in ledger and status [test_full_suite_confirmed_global_verify]
  - AC: Implement scripts/sync_skill.py supporting --check --target <path> which exits 0 only when all destination file hashes match source, with a temp-dir test and no usernames or absolute paths in plan or config [test_sync_skill_script_and_hash_comparison]

## Task Specification
# T0: Repair test suite baseline & sync global skill copy
id: T0
requirements: R0
depends_on:
allowed_files: tests/test_osr.py, scripts/sync_skill.py, tests/test_sync_skill.py, pyproject.toml
forbidden_files: 
context_files: .ai/PLAN.md, pyproject.toml, CHANGELOG.md, evals/eval_suite.py
verify: python -m unittest tests.test_osr tests.test_sync_skill -v

## Goal
Repair baseline test failures in tests/test_osr.py (dynamic version consistency check across pyproject.toml, eval_suite.py, CHANGELOG.md, and osr.VERSION; per-vector benchmark assertions without hardcoded counts or test weakening) and implement scripts/sync_skill.py with hash comparison.

## Constraints
- Python 3.8+ standard library only.
- No test methods removed; assertion counts not reduced (no weakening).
- Version consistency asserts osr.VERSION == pyproject version == eval_suite version == top CHANGELOG entry.
- Benchmark test asserts per required vector ID (v["status"] == "CAUGHT"), not hardcoded count 10.
- scripts/sync_skill.py --check --target <path> exits 0 only when all destination file hashes match source.
- No usernames or absolute paths in plan or config.

## Do not
- Do not weaken or delete any existing test or assertion.
- Do not hardcode version strings or caught vector totals.
- Do not use absolute user paths.

## Definition of done
- Failing tests reproduced in tests/test_osr.py and tests/test_sync_skill.py.
- All tests in tests/test_osr.py and tests/test_sync_skill.py pass cleanly.
- scripts/sync_skill.py --check --target <path> passes on temp-dir test.
- Full test suite green via confirmed global_verify command with pass count recorded.


## Code Diff
```diff
diff --git a/.ai/AUDIT.md b/.ai/AUDIT.md
index 5937fbe..2df80a2 100644
--- a/.ai/AUDIT.md
+++ b/.ai/AUDIT.md
@@ -1,4 +1,4 @@
-# Audit  (2026-10-22T04:25:49Z)
+# Audit  (2026-10-22T13:48:55Z)
 
 Ledger integrity: ok. Plan approved and unchanged: True.
 
@@ -6,12 +6,17 @@ Ledger integrity: ok. Plan approved and unchanged: True.
 
 | Req | Check | Tasks | Status | Evidence |
 |---|---|---|---|---|
-| R1 | auto | T1 | VERIFIED | integrations/antigravity/stop_hook.py:42 (tests: test_stop_hook_contract) |
-| R2 | auto | T2 | VERIFIED | scripts/osr.py:1879 (tests: test_fixture_capture_and_seam_source) |
-| R3 | auto | T3 | VERIFIED | scripts/osr.py:745 (tests: test_verify_zero_tests_rejected) |
-| R4 | auto | T4 | VERIFIED | scripts/osr.py:132 (tests: test_tautological_assertion_ast) |
-| R5 | auto | T5 | VERIFIED | scripts/osr.py:2190 (tests: test_external_anchor_verification) |
-| R6 | auto | T6 | VERIFIED | scripts/osr.py:1554 (tests: test_honest_reporting_and_heuristics) |
+| R0 | auto | T0 | INCOMPLETE |  |
+| R1 | auto | T1 | VERIFIED | integrations/antigravity/stop_hook.py:42 (tests: test_ledger_evidence_classes_recorded, test_audit_weakest_evidence_class, test_ledger_verify_v031_backwards_compatible, test_vector_v14_evidence_classes_gate) |
+| R2 | auto | T2 | VERIFIED | scripts/osr.py:1879 (tests: test_stop_hook_contract_schema, test_stop_hook_loop_guard_n3, test_pre_tool_use_schema_conformance, test_vector_v15_stop_hook_gate) |
+| R4b | manual | T4b | PENDING-HUMAN (UNVERIFIED) | scripts/test_agent_tty.py |
+| R4 | auto | T4 | VERIFIED | scripts/osr.py:132 (tests: test_sensitive_flags_governance, test_cmd_set_secret_rotation_and_audit_flag, test_human_commands_verify_secret_fingerprint, test_approval_fail_closed_no_tty, test_approval_refuse_legacy_unsalted, test_approval_secret_scrypt_terminal, test_audit_records_unprotected_approvals, test_pre_tool_deny_secret_access, test_vector_v17_approval_secret_gate) |
+| R3 | auto | T3 | VERIFIED | scripts/osr.py:745 (tests: test_test_config_file_list_defined, test_config_drift_check_verify_and_quick, test_quick_requires_confirmed_verify, test_quick_rejects_weak_commands, test_quick_enforces_ledger_chain, test_quick_refuses_during_in_progress_tasks, test_quick_records_skipped_gates, test_vector_v16_quick_path_gate) |
+| R5a | auto | T5a | INCOMPLETE |  |
+| R5b | auto | T5b | INCOMPLETE |  |
+
+## Tasks not done
+T0, T4b, T5a, T5b
 
 ## Waivers (decisions to bypass a flag)
 - T1 unanchored-mock:tests/test_hardening_hypotheses.py: tests/test_hardening_hypotheses.py is the Phase B adversarial test suite testing mock evasion across hypotheses, not an unanchored mock for T1 (approved by AI only)
diff --git a/.ai/PLAN.md b/.ai/PLAN.md
index 75cc226..bc7d132 100644
--- a/.ai/PLAN.md
+++ b/.ai/PLAN.md
@@ -1,43 +1,106 @@
-# Plan: osr v0.3.1 Hardening
+# Plan: osr v0.3.2 Hardening & Bypass Mitigation
 
 ## Goal
-Audit and harden osr v0.3.0 against confirmed adversarial evasion vectors (H12 hook schema contract, H1 fixture capture & mandatory conformance, H2 bogus seam source detection, H6/V12 zero-test verify detection, H5/V11 tautological assertion AST inspection, H11 out-of-band anchor support, and Phase A CI/doc truthfulness), preserving stdlib-only operation and backwards compatibility.
+Close the verification bypasses identified during the v0.3.1 implementation audit across the MUST tier (Phases 0 through 5): repair the test baseline and sync global skill copy (R0), introduce explicit evidence classes in the ledger and audit (R1), implement official Antigravity Stop hook schema with loop guard and PreToolUse contract (R2), harden `osr quick` with command confirmation, chain verification, and test-config protections (R3), replace readable approval secrets with salted scrypt interactive terminal prompts failing closed without TTY (R4), empirically verify agent terminal interactive prompt behavior (R4b), and enforce test-run integrity with positive counts, new test execution verification, assertionless test scanning, and selection flag controls across verify and quick (R5a, R5b).
 
 ## Non-goals
-- Parsing language-specific schemas or non-Python ASTs inside `scripts/osr.py` (standard-library only).
-- Breaking existing v0.2.0 or v0.3.0 task cards that declare no seams or kinds.
+- Parsing non-Python ASTs or language-specific schemas inside `scripts/osr.py` (standard-library only).
+- Breaking backwards compatibility for existing cards without new optional fields.
 - Pushing to or merging into `main` branch.
+- Weakening existing test assertions or benchmark vectors (no test removed, assertion counts not reduced).
+
+## Task Order
+1. R0: Repair test suite baseline & sync global skill copy
+2. R1: Evidence classes in the ledger and audit
+3. R2: Stop hook correctness and loop guard
+4. R4b: Antigravity agent terminal interactive prompt assessment (manual signoff)
+5. R4: Approval secret unreadable by agent (scrypt & terminal prompt)
+6. R3: Harden quick path
+7. R5a: Positive test counts and new test execution
+8. R5b: Assertionless tests, selection flags, and extra tautologies
 
 ## Requirements
-- R1: Antigravity stop hook contract compliance
-  - AC: integrations/antigravity/stop_hook.py returns valid Antigravity Stop schema with decision and reason fields [test_stop_hook_contract]
+- R0: Repair test suite baseline & sync global skill copy
+  - AC: Fix the 3 failing tests in tests/test_osr.py by asserting version consistency across the project (osr.VERSION == pyproject version == eval_suite version == top CHANGELOG entry) and asserting benchmark results per required vector ID without hardcoded counts and without weakening (no test removed, assertion counts not reduced) [test_baseline_repair_green]
+  - AC: Execute a confirmed global_verify command validating the full test suite is green with pass count recorded in ledger and status [test_full_suite_confirmed_global_verify]
+  - AC: Implement scripts/sync_skill.py supporting --check --target <path> which exits 0 only when all destination file hashes match source, with a temp-dir test and no usernames or absolute paths in plan or config [test_sync_skill_script_and_hash_comparison]
   - Check: auto
-- R2: Seam integrity, tool-captured fixtures, and mandatory conformance
-  - AC: osr fixture-capture executes confirmed commands recording stdout, seam cards with fixtures mandate conformance commands or report unverified, and seam sources in test/mock paths are rejected [test_fixture_capture_and_seam_source]
+
+- R1: Evidence classes in the ledger and audit
+  - AC: Ledger check entries record explicit evidence class with no default class (any entry type without a declared class fails tests and audit); re-justified classification: observed (direct execution outcome: verify exit code, quick exit code, seam conformance execution exit code, fixture capture exit code), heuristic (static approximation or unverified output: stdout-parsed positive test counts, scope lock check, placeholder pattern scan, reference integrity check, tautological assertion AST/regex scan, assertionless test scan, unapproved selection flag scan), or attested (human declarations: approve-plan human approval, signoff manual requirement signoff [retaining HUMAN-SIGNED status], waive check flag waiver, reset human task reset) [test_ledger_evidence_classes_recorded]
+  - AC: Audit requirement traceability table displays evidence classes present per requirement, and VERIFIED status strictly requires >=1 observed entry (failing down to HEURISTIC-ONLY or ATTESTED-ONLY otherwise); legacy unclassified ledger entries produce UNCLASSIFIED-LEGACY with exit code 2 (no auto-classification) [test_audit_weakest_evidence_class]
+  - AC: osr ledger-verify verifies hash-chain integrity on legacy v0.3.1 ledger fixtures without errors [test_ledger_verify_v031_backwards_compatible]
+  - AC: Benchmark vector V14 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches unclassified or disguised heuristic evidence with gate id gate_evidence_classes [test_vector_v14_evidence_classes_gate]
   - Check: auto
-- R3: Zero-test runner output detection for verify commands (V12)
-  - AC: osr verify parses test runner stdout and fails with exit code 1 when zero tests are collected or executed [test_verify_zero_tests_rejected]
+
+- R2: Stop hook correctness and loop guard
+  - AC: Stop hook emits official schema (decision and reason) conforming to captured vendor contract docs/vendor/antigravity-hooks-2026-10-22.md, with stop-hook tests dynamically extracting examples from the vendor doc at test time as test fixtures [test_stop_hook_contract_schema]
+  - AC: Stop hook inspects osr status --json and allows termination after N=3 consecutive identical blocks tracked in loop-guard counter file .ai/loop_guard.json, or when human action is pending; guard-allowed terminations are logged in the ledger and displayed in audit and status [test_stop_hook_loop_guard_n3]
+  - AC: PreToolUse hook conforms to the schema in the vendor doc (docs/vendor/antigravity-hooks-2026-10-22.md), blocking protected path modifications and dangerous commands [test_pre_tool_use_schema_conformance]
+  - AC: Benchmark vector V15 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches stop hook contract evasion with gate id gate_stop_hook_contract [test_vector_v15_stop_hook_gate]
   - Check: auto
-- R4: Tautological assertion detection via Python AST and JS regex (V11)
-  - AC: osr check inspects Python AST for constant assertions and self-comparisons and flags JavaScript expect self-match regex [test_tautological_assertion_ast]
+
+- R4b: Antigravity agent terminal interactive prompt assessment
+  - AC: Attempt to run approve-plan from the real Antigravity agent terminal, document whether it can answer an interactive prompt or fails closed without TTY, apply the decision rule (if the agent terminal can answer prompts, document no protection in that harness, recommend separate OS user or CI-only approvals, and open a follow-up issue), and record manual human signoff [manual_agent_terminal_tty_signoff]
+  - Check: manual
+  - Script: scripts/test_agent_tty.py
+
+- R4: Approval secret unreadable by agent (scrypt & terminal prompt)
+  - AC: Define sensitive flags (selection flags, custom-parser exemption, --allow-config); any waiver or bypass of sensitive flags requires human authorization with secret verification recorded in the ledger [test_sensitive_flags_governance]
+  - AC: Implement set-secret command prompting for password with confirmation, generating salted hashlib.scrypt hash, and writing an attested ledger entry containing the secret hash fingerprint; first set happens before any agent session; any subsequent set-secret requires verifying the old secret; audit flags any set-secret performed after plan approval [test_cmd_set_secret_rotation_and_audit_flag]
+  - AC: Every human-only command (approve-plan, unblock, reset, signoff, waive for sensitive flags) prompts for the secret and verifies the computed hash matches the last fingerprint recorded in the ledger [test_human_commands_verify_secret_fingerprint]
+  - AC: Approval commands fail closed with explicit error when no controlling TTY/console is present [test_approval_fail_closed_no_tty]
+  - AC: Refuse legacy unsalted SHA-256 secret in config until set-secret command is rerun [test_approval_refuse_legacy_unsalted]
+  - AC: Remove --secret CLI flag and OSR_APPROVAL_SECRET environment variable from approval commands to prevent process-table or environment snooping [test_approval_secret_scrypt_terminal]
+  - AC: Audit records unprotected approvals with prominent warning [test_audit_records_unprotected_approvals]
+  - AC: PreToolUse deny rules prevent agent tool calls from inspecting or modifying approval secret files [test_pre_tool_deny_secret_access]
+  - AC: Benchmark vector V17 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches approval secret disclosure/bypass with gate id gate_approval_scrypt_terminal [test_vector_v17_approval_secret_gate]
   - Check: auto
-- R5: Out-of-band ledger anchor support and trust boundary documentation
-  - AC: osr anchor and ledger-verify support optional external anchor file paths with documented threat model [test_external_anchor_verification]
+
+- R3: Harden quick path
+  - AC: Define minimal test-config file list (pytest.ini, setup.cfg, tox.ini, pyproject.toml, jest.config.js, jest.config.ts, jest.config.json, vitest.config.js, vitest.config.ts, package.json [scripts block only], .eslintrc.js, .eslintrc.json, tsconfig.json) [test_test_config_file_list_defined]
+  - AC: Test-config drift check runs in both osr verify and osr quick against fingerprints recorded at confirm-commands (not uncommitted changes) and refuses execution unless bypassed by --allow-config (which requires the approval secret and records an attested ledger entry) [test_config_drift_check_verify_and_quick]
+  - AC: osr quick requires confirmed verify commands matching .ai/config.json and rejects unconfirmed commands [test_quick_requires_confirmed_verify]
+  - AC: osr quick rejects trivial commands and weak verify patterns (token existence checks) [test_quick_rejects_weak_commands]
+  - AC: osr quick enforces ledger hash-chain integrity verification (require_chain=True) [test_quick_enforces_ledger_chain]
+  - AC: osr quick refuses execution during in-progress task attempts [test_quick_refuses_during_in_progress_tasks]
+  - AC: osr quick records skipped verification gates explicitly in ledger entry and stdout output [test_quick_records_skipped_gates]
+  - AC: Benchmark vector V16 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches unconfirmed quick command and broken ledger chain with gate id gate_quick_confirmation_and_chain [test_vector_v16_quick_path_gate]
+  - Check: auto
+
+- R5a: Positive test counts and new test execution
+  - AC: Record base commit hash at osr start; newly added or modified test functions are determined via git diff against base_commit (falling back to stored copies saved at osr start, else marking UNVERIFIED) [test_record_base_commit_and_diff]
+  - AC: Parse positive test execution counts from runner output captured via fixture-capture from real test runs; unittest and pytest are verified against captured seam sources; jest and vitest are experimental notes with no declared seam (producing UNVERIFIED unless exempted by a human-approved osr waive for sensitive flags recorded in the ledger) [test_runner_positive_counts_in_scope]
+  - AC: Verify newly added or modified test function names appear in runner output; runners are invoked with standard environment variables LC_ALL=C and PYTHONIOENCODING=utf-8, preferring locale-independent parsers; non-English or unparseable runner output produces UNVERIFIED status [test_new_tests_executed_and_locale_handling]
+  - AC: When test runner output contains no individual test names (non-verbose runner execution), verify command flags missing test names and requires verbose flag or marks UNVERIFIED with actionable warning [test_runner_non_verbose_warning]
+  - AC: Benchmark vector V18 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches zero-test and unparsed runner outputs with gate id gate_runner_positive_counts [test_vector_v18_runner_counts_gate]
   - Check: auto
-- R6: Heuristic transparency, negative-test documentation, and honest CI/benchmark reporting
-  - AC: Heuristic warnings are explicitly labeled as heuristics, CI matrix includes Python 3.8, and README/CHANGELOG report honest denominators [test_honest_reporting_and_heuristics]
+
+- R5b: Assertionless tests, selection flags, and extra tautologies
+  - AC: Check scans test diffs and flags assertionless test functions via AST (Python) and regex (JS/TS), tested against literal (test_assertionless_literal), disguised (test_assertionless_disguised), and subtle (test_assertionless_subtle) evasion patterns [test_assertionless_detection]
+  - AC: Check rejects unapproved test runner selection flags in verify commands (-k, -m, -t, --testNamePattern, test path filters) unless exempted by a human-approved osr waive for sensitive flags recorded in the ledger (not a task card field), tested with literal (test_selection_flags_literal), disguised (test_selection_flags_disguised), and subtle (test_selection_flags_subtle) variants [test_selection_flags_detection]
+  - AC: Check inspects extended tautological assertions (assert True, self == self, expect(x).toBe(x), Boolean literals, tautological boolean expressions), tested with literal (test_tautology_literal), disguised (test_tautology_disguised), and subtle (test_tautology_subtle) variants [test_tautology_extended_detection]
+  - AC: Integrity checks (assertionless tests, selection flags, tautologies) are wired into both osr verify and osr quick [test_integrity_checks_wired_verify_and_quick]
+  - AC: Benchmark vector V19 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches assertionless tests and evasion variants with gate id gate_assertionless_and_tautology_scan [test_vector_v19_assertionless_gate]
   - Check: auto
 
 ## Seams
 | seam id | consumer | provider | authoritative source | how it is checked |
 |---|---|---|---|---|
-| antigravity_hook | integrations/antigravity/stop_hook.py | Antigravity Runtime | integrations/antigravity/stop_hook.py | contract-test |
-| runner_output | scripts/osr.py | Test Runners (unittest/pytest/jest) | scripts/osr.py | parser-contract-test |
+| antigravity_hook | integrations/antigravity/stop_hook.py | Antigravity Runtime | docs/vendor/antigravity-hooks-2026-10-22.md | contract-test: python -m unittest tests/test_stop_hook.py |
+| runner_output_unittest | scripts/osr.py | unittest Runner | docs/vendor/runner_outputs/unittest_output.txt | parser-conformance-test: python -m unittest tests/test_runner_parsers.py |
+| runner_output_pytest | scripts/osr.py | pytest Runner | docs/vendor/runner_outputs/pytest_output.txt | parser-conformance-test: python -m unittest tests/test_runner_parsers.py |
 
 ## Assumptions
 - [x] Python 3.8+ standard library remains the sole runtime dependency for `scripts/osr.py`.
-- [x] Cards with no seams or kinds behave exactly as in v0.2.0.
-- [x] The human operator approves the hardening plan and reviews independence markers.
+- [x] All new fields and flags are optional; existing projects without them behave as in v0.3.1.
+- [x] Antigravity Stop and PreToolUse hook specifications and examples are anchored to captured vendor documentation `docs/vendor/antigravity-hooks-2026-10-22.md`.
+- [x] Loop-guard counter is persisted across hook invocations in `.ai/loop_guard.json`.
+- [x] Vector suite does not contain V13; V13 is reserved and new vectors continue sequentially as V14 through V19.
+- [x] Benchmark vectors V14 through V19 require control runs (cheat removed passes) and must fail on v0.3.1 baseline and pass on v0.3.2.
+- [x] Jest and Vitest runners are experimental notes with no declared seam; unittest and pytest are the sole active runner output seams.
 
 ## Open questions
-- None.
+- OQ1 (OPEN - pending R4b manual signoff): Does the Antigravity agent terminal allow interactive getpass input, or will approve-plan fail closed when run non-interactively? (Evaluated via scripts/test_agent_tty.py and documented in .ai/TTY_ANALYSIS.md; kept open until human signoff in R4b).
+- [x] OQ2: How should test runners not installed locally (e.g. Jest/Vitest) be validated in CI without adding heavyweight npm dependencies? (Resolved: unittest and pytest are the sole in-scope seams verified via fixture-capture from real runs; jest and vitest are experimental notes with no seam and produce UNVERIFIED unless waived).
+- [x] OQ3: How are localized test runner outputs handled if a non-English OS environment runs tests? (Resolved: Test runners are invoked with standard environment variables LC_ALL=C and PYTHONIOENCODING=utf-8, and regex parsers prefer locale-independent patterns; non-English output is marked UNVERIFIED).
diff --git a/.ai/STATE.md b/.ai/STATE.md
index 1f1046e..98f8d5a 100644
--- a/.ai/STATE.md
+++ b/.ai/STATE.md
@@ -2,11 +2,13 @@
 
 Ledger: ok
 
+- T0: in_progress (attempt 1, failures 0)
 - T1: done (attempt 2, failures 1)
 - T2: done (attempt 1, failures 1)
 - T3: done (attempt 1, failures 1)
 - T4: done (attempt 1, failures 1)
-- T5: done (attempt 1, failures 0)
-- T6: done (attempt 1, failures 1)
+- T4b: todo (attempt 0, failures 0)
+- T5a: todo (attempt 0, failures 0)
+- T5b: todo (attempt 0, failures 0)
 
-NEXT: osr audit
+NEXT: Write .ai/reviews/T0.spec.md (template assets/spec-review.md), then: osr review T0 spec --reviewer <name>
diff --git a/.ai/config.json b/.ai/config.json
index 1e07362..12ff38b 100644
--- a/.ai/config.json
+++ b/.ai/config.json
@@ -54,10 +54,15 @@
     "test": {
       "cmd": "python -m unittest discover -s tests -v",
       "verified": true
+    },
+    "smoke": {
+      "cmd": "python -m unittest tests.test_honest_reporting tests.test_zero_runner -v",
+      "verified": true
     }
   },
   "global_verify": [
     "test"
   ],
-  "extra_placeholder_patterns": []
+  "extra_placeholder_patterns": [],
+  "checkers": []
 }
diff --git a/.ai/ledger.jsonl b/.ai/ledger.jsonl
index 0c62b6d..e802f9c 100644
--- a/.ai/ledger.jsonl
+++ b/.ai/ledger.jsonl
@@ -205,3 +205,20 @@
 {"seq": 205, "ts": "2026-10-22T03:50:13Z", "type": "review", "task": "T6", "attempt": 1, "data": {"stage": "spec", "verdict": "PASS", "fp": "4cba2486560260244488dca0ae93ab820c3a8cbe06a53a81fe92c8fb35a4735f", "file_sha": "ad3b272304a8a9d06367bf8042e13031abeab425767daee9acb7f36ddea4924d", "reviewer": "independent-reviewer", "self_review": false, "items": {"R6": {"status": "PASS", "evidence": "scripts/osr.py:1554"}}}, "prev": "cc670fccf30a84ab3bcd2f2dcee5a4a3775e30901ff2283c7ee4b9e98855f3bb", "hash": "6637826f43e7efe6ecee28009430a3d09013253d98de5b05f890ec9966cdbc76"}
 {"seq": 206, "ts": "2026-10-22T03:50:20Z", "type": "review", "task": "T6", "attempt": 1, "data": {"stage": "quality", "verdict": "PASS", "fp": "4cba2486560260244488dca0ae93ab820c3a8cbe06a53a81fe92c8fb35a4735f", "file_sha": "3247e37effb99338179f7f1ef0b083241f925325d058079f164aea59a22cce14", "reviewer": "independent-reviewer", "self_review": false, "items": {"C1": "PASS", "C2": "PASS", "C3": "PASS", "C4": "PASS", "C5": "PASS", "C6": "PASS", "C7": "PASS", "C8": "PASS"}}, "prev": "6637826f43e7efe6ecee28009430a3d09013253d98de5b05f890ec9966cdbc76", "hash": "e84541472782f6ab4bddc5f9bc095faac973030f1cf3819a6cce226c09cb52fd"}
 {"seq": 207, "ts": "2026-10-22T03:50:28Z", "type": "done", "task": "T6", "attempt": 1, "data": {"fp": "4cba2486560260244488dca0ae93ab820c3a8cbe06a53a81fe92c8fb35a4735f"}, "prev": "e84541472782f6ab4bddc5f9bc095faac973030f1cf3819a6cce226c09cb52fd", "hash": "b6a762e80c1612ef67e2bf18423f898590de58474152b9d3dd5af48ab62d3357"}
+{"seq": 208, "ts": "2026-10-22T06:59:01Z", "type": "fixture_add", "task": null, "attempt": null, "data": {"path": "docs/vendor/antigravity-hooks-2026-10-22.md", "seam": "antigravity_hook", "source": "Antigravity CLI built-in agy-customizations/docs/hooks.md captured 2026-10-22", "sha256": "f247698e6e9b5eda2920574c365d2689ae951dbfd8100530bc399be56e077462"}, "prev": "b6a762e80c1612ef67e2bf18423f898590de58474152b9d3dd5af48ab62d3357", "hash": "ed8a3bbb774415d19e6b8f6c0a75e2f51e8d0760ef493b2326fc15549eb58f24"}
+{"seq": 209, "ts": "2026-10-22T07:28:05Z", "type": "fixture_add", "task": null, "attempt": null, "data": {"path": "docs/vendor/runner_outputs/runner_specs.md", "seam": "runner_output", "source": "Captured runner outputs from real runs", "sha256": "4137482527ae0e223e1d2d9bf8b67aabbc40e38fdc2219a4e85c6c590d988a30"}, "prev": "ed8a3bbb774415d19e6b8f6c0a75e2f51e8d0760ef493b2326fc15549eb58f24", "hash": "866b8abd7b3dccbe1526e3a4398cb5878ad58e68acaf9dfeea76c1b88785ca55"}
+{"seq": 210, "ts": "2026-10-22T07:53:41Z", "type": "fixture_add", "task": null, "attempt": null, "data": {"path": "docs/vendor/runner_outputs/unittest_output.txt", "seam": "runner_output_unittest", "source": "Captured real unittest output", "sha256": "94f42096d03ac8ef3aa09206921fce42774374df3346d46123fba1d9ca5d4ec2"}, "prev": "866b8abd7b3dccbe1526e3a4398cb5878ad58e68acaf9dfeea76c1b88785ca55", "hash": "a38163749a8781a08ad805a67d856d155ac4a9814ff87cdc3727f4cc189443a3"}
+{"seq": 211, "ts": "2026-10-22T07:53:42Z", "type": "fixture_add", "task": null, "attempt": null, "data": {"path": "docs/vendor/runner_outputs/pytest_output.txt", "seam": "runner_output_pytest", "source": "Captured real pytest output", "sha256": "bc02b728b895afe7791d77c1a542b87c0e98be1b9950ede38748b32bcb872ec0"}, "prev": "a38163749a8781a08ad805a67d856d155ac4a9814ff87cdc3727f4cc189443a3", "hash": "a421ce4fcd724fbcbc31666f710443b7d2bf2711c8061346c2b845917124e5d5"}
+{"seq": 212, "ts": "2026-10-22T07:53:42Z", "type": "fixture_add", "task": null, "attempt": null, "data": {"path": "docs/vendor/runner_outputs/jest_output.txt", "seam": "runner_output_jest", "source": "Captured real jest output", "sha256": "ee9371b956a73bebebede682677ed74ab299a844d935fafb3f7631831c180eab"}, "prev": "a421ce4fcd724fbcbc31666f710443b7d2bf2711c8061346c2b845917124e5d5", "hash": "74b0f88a87ef86d6f2594844e07284221ba3c93d3b323f21cfefd43c7b86507a"}
+{"seq": 213, "ts": "2026-10-22T07:53:42Z", "type": "fixture_add", "task": null, "attempt": null, "data": {"path": "docs/vendor/runner_outputs/vitest_output.txt", "seam": "runner_output_vitest", "source": "Captured real vitest output", "sha256": "5cbc6fb9030674c8dc44673b8a5c60681bbdf2a4a618f2e10d68650c3f906713"}, "prev": "74b0f88a87ef86d6f2594844e07284221ba3c93d3b323f21cfefd43c7b86507a", "hash": "4e4039e5e4913f312bfb466e1a5be4491eed80d2fe0795d56fa432a42a392f0b"}
+{"seq": 214, "ts": "2026-10-22T08:20:14Z", "type": "plan_approved", "task": null, "attempt": null, "data": {"by": "Sam", "plan_hash": "54d336d3f053dba25e0baaef5ea002d504a13f26b6cea29f6430bf4ca765acf2", "config_hash": "bb541d449833ac034f127b3987619424ea8452694f8c6c8cd953b0fd0f672ad9"}, "prev": "4e4039e5e4913f312bfb466e1a5be4491eed80d2fe0795d56fa432a42a392f0b", "hash": "f679853386566ddcba7aad49983d2e4a8a652cd3385bb314c6b51205bd4be9a9"}
+{"seq": 215, "ts": "2026-10-22T08:40:46Z", "type": "start", "task": "T0", "attempt": 1, "data": {"model": "gemini-3.8-flash", "input_hash": "402cd792540ef1f520f7e065562b9b2cd0ec129bacf4060a1aa5d71227289664", "baseline": {"test": {"ok": false, "exit": 1, "sha": "e05f0f44f0493cbc98913363388f287d08b8e5992d0b785bdd19388bd409be6b"}, "task_0": {"cmd": "python -m unittest tests.test_osr tests.test_sync_skill -v", "ok": false, "exit": 1, "sha": "88dc3f1bfaa7d13db314b15a0160e69f4106e797f6c3ff296d7d788abcf30cb4"}}}, "prev": "f679853386566ddcba7aad49983d2e4a8a652cd3385bb314c6b51205bd4be9a9", "hash": "5b756921d11dd5c5e70df85ab54485998a83fc0979af2a4e752b2c65dd26a92d"}
+{"seq": 216, "ts": "2026-10-22T09:09:37Z", "type": "plan_approved", "task": null, "attempt": null, "data": {"by": "Sam", "plan_hash": "54d336d3f053dba25e0baaef5ea002d504a13f26b6cea29f6430bf4ca765acf2", "config_hash": "d79132ae2f18a0893dc4ee68ee67a811e7722350f79476de753bf09f84cacbc5"}, "prev": "5b756921d11dd5c5e70df85ab54485998a83fc0979af2a4e752b2c65dd26a92d", "hash": "19f9584ae6d30b1f139ee53cc9c45d0e804d6c451d1a70041e8adcf24f4f1e6f"}
+{"seq": 217, "ts": "2026-10-22T09:09:55Z", "type": "cmd_confirm", "task": null, "attempt": null, "data": {"name": "smoke", "cmd": "python -m unittest tests.test_honest_reporting tests.test_zero_runner -v", "ok": true, "exit": 0, "output_sha": "948a42b6edabeae0a0a231abb8800fe4eca86ad99fd062b99e5352c0f337a8c2"}, "prev": "19f9584ae6d30b1f139ee53cc9c45d0e804d6c451d1a70041e8adcf24f4f1e6f", "hash": "8943b8da8f379a9a82a1b0a1cba33167e76dfa143f05a343c5bd5f9de21cae89"}
+{"seq": 218, "ts": "2026-10-22T09:40:52Z", "type": "check", "task": "T0", "attempt": 1, "data": {"ok": true, "fp": "245238b1d5c7ef55953634f036e7d3e49900a11fcf56b59a5d08af9be3b8e050", "flags": [], "unchecked": []}, "prev": "8943b8da8f379a9a82a1b0a1cba33167e76dfa143f05a343c5bd5f9de21cae89", "hash": "55ea10c9ddba65b778a923c0c10544f45e7e5125d122807bc97195203b10b489"}
+{"seq": 219, "ts": "2026-10-22T09:50:32Z", "type": "check", "task": "T0", "attempt": 1, "data": {"ok": true, "fp": "245238b1d5c7ef55953634f036e7d3e49900a11fcf56b59a5d08af9be3b8e050", "flags": [], "unchecked": []}, "prev": "55ea10c9ddba65b778a923c0c10544f45e7e5125d122807bc97195203b10b489", "hash": "81992468154bebf209a21e025857b7991fb1fbe895d8034bfbea65a67c96a5d1"}
+{"seq": 220, "ts": "2026-10-22T09:50:32Z", "type": "verify", "task": "T0", "attempt": 1, "data": {"ok": true, "fp": "245238b1d5c7ef55953634f036e7d3e49900a11fcf56b59a5d08af9be3b8e050", "results": [{"cmd": "python -m unittest tests.test_honest_reporting tests.test_zero_runner -v", "exit": 0, "timeout": false, "suspect": false, "secs": 5.6, "output_sha": "608bef46cdf0f1c7024d557cee79271cebb82d6e6b05539e1a57df259c8ab073", "log": "20261022-104057-T0-smoke.log", "ok": true, "name": "smoke"}, {"cmd": "python -m unittest tests.test_osr tests.test_sync_skill -v", "exit": 0, "timeout": false, "suspect": false, "secs": 573.9, "output_sha": "224b94db13d87ccd90ddc541f809e9897d4ec33363abf3f52aa9acd06a841c9e", "log": "20261022-105031-T0-task.log", "ok": true, "name": "task"}], "red_green": {}, "passed_tests": ["test_adversarial_eval_suite_benchmarks_catch_rate", "test_anchor_verification_detects_ledger_rollback", "test_antigravity_pre_tool_hook_blocks_human_commands", "test_antigravity_pre_tool_hook_blocks_out_of_scope_edits", "test_antigravity_stop_hook_forces_continuation_when_tasks_pending", "test_approval_secret_enforcement", "test_blind_retry_is_blocked_and_triage_forces_a_change", "test_card_with_fixture_and_conformance_verifies_cleanly", "test_cheat_verify_true_rejected", "test_config_tampering_voids_plan_approval", "test_criteria_test_traceability_blocks_done_when_missing", "test_fabricated_review_evidence_is_rejected", "test_fixture_add_and_verify_hash_integrity", "test_full_happy_path", "test_git_pre_commit_hook", "test_honest_reporting_and_heuristics", "test_js_references_and_weakened_tests_are_flagged", "test_json_output_and_exit_codes", "test_kind_realtime_requires_realtime_appendix_in_quality_review", "test_ledger_locking_concurrency", "test_ledger_tampering_is_detected", "test_manual_check_requirement_shows_unverified_until_signoff_audit_exit_2", "test_manual_requirement_cannot_pass", "test_negative_tests_enforced_per_seam_and_verified_in_test_output", "test_next_walks_the_workflow", "test_no_tests_ran_is_failure", "test_phase6_benchmark_and_honest_reporting", "test_phase6_version_and_docs_integrity", "test_placeholder_and_hallucinated_import_are_caught", "test_plan_must_be_approved_and_stay_unchanged", "test_pluggable_checkers_in_config_block_on_failure", "test_quality_review_seam_citations_enforcement", "test_quick_path_rejects_scope_violation", "test_quick_path_verifies_without_task_cards", "test_red_green_baseline_recorded_at_start", "test_review_on_stale_code_and_done_gate", "test_review_pack_bundles_diff_card_criteria_without_builder_logs", "test_review_pack_includes_adversarial_prompt_seams_and_authoritative_sources", "test_scope_violation_blocks_verify", "test_seams_plan_check_passes_with_seams_table", "test_seams_plan_check_warning_when_seams_table_missing", "test_spec_triage_blocks_until_human_unblocks", "test_sync_skill_file_set_and_check", "test_sync_skill_negative_differing_file", "test_sync_skill_negative_extra_file", "test_sync_skill_negative_missing_file", "test_sync_skill_script_exists", "test_task_check_enforces_seam_authoritative_source_in_context_files", "test_unanchored_mock_heuristic_flags_mock_without_fixture_and_waiver_resolves", "test_unconfirmed_commands_block_approval", "test_verify_command_must_be_confirmed", "test_verify_zero_tests_rejected", "test_waiver_rules"]}, "prev": "81992468154bebf209a21e025857b7991fb1fbe895d8034bfbea65a67c96a5d1", "hash": "16da640e69d5fd6f31e181684ba68c2435dea879c203772b2affd9e6d8662a31"}
+{"seq": 221, "ts": "2026-10-22T10:03:24Z", "type": "plan_approved", "task": null, "attempt": null, "data": {"by": "Sam", "plan_hash": "54d336d3f053dba25e0baaef5ea002d504a13f26b6cea29f6430bf4ca765acf2", "config_hash": "f087dce4b37c0eb4192fc45295c8ef494155cd04e3d910f3a9a336f75d552420"}, "prev": "16da640e69d5fd6f31e181684ba68c2435dea879c203772b2affd9e6d8662a31", "hash": "43c5d91e3c94649042d2573701f31a7aaa80860ae943603fe012e419cb548731"}
+{"seq": 222, "ts": "2026-10-22T10:11:30Z", "type": "cmd_confirm", "task": null, "attempt": null, "data": {"name": "test", "cmd": "python -m unittest discover -s tests -v", "ok": true, "exit": 0, "output_sha": "bac6f676a9f905d7ad1ce807a3d37df2003dfcca6aeef68cbc29056fab44a084"}, "prev": "43c5d91e3c94649042d2573701f31a7aaa80860ae943603fe012e419cb548731", "hash": "f6d3685c56b6eef96bdad13b27948629dc98e8d779a886ccc5e00190c37287be"}
+{"seq": 223, "ts": "2026-10-22T10:11:35Z", "type": "cmd_confirm", "task": null, "attempt": null, "data": {"name": "smoke", "cmd": "python -m unittest tests.test_honest_reporting tests.test_zero_runner -v", "ok": true, "exit": 0, "output_sha": "a1f2710b1ffaf0096ed25c90708d8c0e029aa3d4d22d342b411a8e9be19ce148"}, "prev": "f6d3685c56b6eef96bdad13b27948629dc98e8d779a886ccc5e00190c37287be", "hash": "48589ea04a54b7deee8e92854893f03ba2a45feb2eb57cf042103c99f2c58ff2"}
+{"seq": 224, "ts": "2026-10-22T10:11:43Z", "type": "plan_approved", "task": null, "attempt": null, "data": {"by": "Sam", "plan_hash": "54d336d3f053dba25e0baaef5ea002d504a13f26b6cea29f6430bf4ca765acf2", "config_hash": "bf3dcfea13afb97dd48615da36ca67d6716ecfd5cee90472eb4ed5378f7383b4"}, "prev": "48589ea04a54b7deee8e92854893f03ba2a45feb2eb57cf042103c99f2c58ff2", "hash": "eb1ab5fdec3c48e45693e2b2a404269e92b925cbed7002ee039acc8bf5036391"}
diff --git a/.ai/state.json b/.ai/state.json
index 18ff336..35a2ee0 100644
--- a/.ai/state.json
+++ b/.ai/state.json
@@ -1,5 +1,5 @@
 {
-  "plan_hash": "e5db1de7985f83443864825f130c5ed8a660bb8420b3f1e0ee90b81c20ce6051",
+  "plan_hash": "54d336d3f053dba25e0baaef5ea002d504a13f26b6cea29f6430bf4ca765acf2",
   "tasks": {
     "T1": {
       "status": "done",
@@ -168,6 +168,30 @@
           "sha": "4e30d2be790d6b4bdf27634cc767a1e36a51272775dc8816b44d47f812d5feec"
         }
       }
+    },
+    "T0": {
+      "status": "in_progress",
+      "attempts": 1,
+      "failures": 0,
+      "model": "gemini-3.8-flash",
+      "input_hash": "402cd792540ef1f520f7e065562b9b2cd0ec129bacf4060a1aa5d71227289664",
+      "triaged_attempt": 0,
+      "blocked": null,
+      "requires": null,
+      "extra_attempts": 0,
+      "baseline": {
+        "test": {
+          "ok": false,
+          "exit": 1,
+          "sha": "e05f0f44f0493cbc98913363388f287d08b8e5992d0b785bdd19388bd409be6b"
+        },
+        "task_0": {
+          "cmd": "python -m unittest tests.test_osr tests.test_sync_skill -v",
+          "ok": false,
+          "exit": 1,
+          "sha": "88dc3f1bfaa7d13db314b15a0160e69f4106e797f6c3ff296d7d788abcf30cb4"
+        }
+      }
     }
   },
   "waivers": [
@@ -179,6 +203,43 @@
     }
   ],
   "signoffs": {},
-  "config_hash": "bb541d449833ac034f127b3987619424ea8452694f8c6c8cd953b0fd0f672ad9",
-  "fixtures": {}
+  "config_hash": "bf3dcfea13afb97dd48615da36ca67d6716ecfd5cee90472eb4ed5378f7383b4",
+  "fixtures": {
+    "docs/vendor/antigravity-hooks-2026-10-22.md": {
+      "sha256": "f247698e6e9b5eda2920574c365d2689ae951dbfd8100530bc399be56e077462",
+      "seam": "antigravity_hook",
+      "source": "Antigravity CLI built-in agy-customizations/docs/hooks.md captured 2026-10-22",
+      "date": "2026-10-22T06:59:01Z"
+    },
+    "docs/vendor/runner_outputs/runner_specs.md": {
+      "sha256": "4137482527ae0e223e1d2d9bf8b67aabbc40e38fdc2219a4e85c6c590d988a30",
+      "seam": "runner_output",
+      "source": "Captured runner outputs from real runs",
+      "date": "2026-10-22T07:28:05Z"
+    },
+    "docs/vendor/runner_outputs/unittest_output.txt": {
+      "sha256": "94f42096d03ac8ef3aa09206921fce42774374df3346d46123fba1d9ca5d4ec2",
+      "seam": "runner_output_unittest",
+      "source": "Captured real unittest output",
+      "date": "2026-10-22T07:53:41Z"
+    },
+    "docs/vendor/runner_outputs/pytest_output.txt": {
+      "sha256": "bc02b728b895afe7791d77c1a542b87c0e98be1b9950ede38748b32bcb872ec0",
+      "seam": "runner_output_pytest",
+      "source": "Captured real pytest output",
+      "date": "2026-10-22T07:53:42Z"
+    },
+    "docs/vendor/runner_outputs/jest_output.txt": {
+      "sha256": "ee9371b956a73bebebede682677ed74ab299a844d935fafb3f7631831c180eab",
+      "seam": "runner_output_jest",
+      "source": "Captured real jest output",
+      "date": "2026-10-22T07:53:42Z"
+    },
+    "docs/vendor/runner_outputs/vitest_output.txt": {
+      "sha256": "5cbc6fb9030674c8dc44673b8a5c60681bbdf2a4a618f2e10d68650c3f906713",
+      "seam": "runner_output_vitest",
+      "source": "Captured real vitest output",
+      "date": "2026-10-22T07:53:42Z"
+    }
+  }
 }
diff --git a/.ai/tasks/T1.md b/.ai/tasks/T1.md
index b76ade6..d8b2842 100644
--- a/.ai/tasks/T1.md
+++ b/.ai/tasks/T1.md
@@ -1,22 +1,27 @@
-# T1: Antigravity stop hook contract compliance
+# T1: Evidence classes in the ledger and audit
 id: T1
 requirements: R1
-seams: antigravity_hook
-allowed_files: integrations/antigravity/stop_hook.py, tests/test_stop_hook.py, tests/test_hardening_hypotheses.py
-context_files: .ai/PLAN.md, integrations/antigravity/stop_hook.py
-verify: python -m unittest tests.test_stop_hook -v
+depends_on: T0
+allowed_files: scripts/osr.py, tests/test_evidence_classes.py, evals/eval_suite.py
+forbidden_files: 
+context_files: .ai/PLAN.md
+verify: python -m unittest tests.test_evidence_classes -v
 
 ## Goal
-Update stop_hook.py so that it complies with the official Antigravity Stop event contract: returning a dictionary containing 'decision': 'continue' and 'reason': '<message>' instead of 'terminationBehavior': 'force_continue'.
+Implement explicit evidence classes (observed, heuristic, attested) in the ledger schema and cmd_audit. VERIFIED status requires >=1 observed check. Legacy unclassified entries report UNCLASSIFIED-LEGACY with exit code 2. Add benchmark vector V14.
 
 ## Constraints
-- Standard library only.
-- Must parse input JSON from stdin safely.
-- If audit has passed, return decision: approve. If unverified tasks or audit failures remain, return decision: continue.
+- Python 3.8+ standard library only.
+- No default class: an entry type without a declared class fails tests/audit.
+- Audit requirement traceability table displays evidence classes present per requirement.
+- osr ledger-verify verifies legacy v0.3.1 ledgers without breaking.
+- Benchmark vector V14 includes control run and literal, disguised, and subtle variants.
 
 ## Do not
-- Do not use PostInvocation schema keys (terminationBehavior) in the Stop hook.
+- Do not assign a default class to unclassified entries.
+- Do not let requirements with heuristic-only evidence report plain VERIFIED.
 
 ## Definition of done
-- tests/test_stop_hook.py reproduces the contract violation initially and passes after the fix.
+- tests/test_evidence_classes.py reproduces evasion and passes after implementation.
+- Benchmark vector V14 catches unclassified or disguised heuristic evidence.
 - osr verify T1 passes.
diff --git a/.ai/tasks/T2.md b/.ai/tasks/T2.md
index 61060a3..f074fce 100644
--- a/.ai/tasks/T2.md
+++ b/.ai/tasks/T2.md
@@ -1,21 +1,27 @@
-# T2: Seam integrity, fixture capture, and mandatory conformance
+# T2: Stop hook correctness and loop guard
 id: T2
 requirements: R2
-allowed_files: scripts/osr.py, tests/test_fixture_capture.py, tests/test_hardening_hypotheses.py
-context_files: .ai/PLAN.md
-verify: python -m unittest tests.test_fixture_capture -v
+depends_on: T1
+seams: antigravity_hook
+allowed_files: integrations/antigravity/stop_hook.py, tests/test_stop_hook.py, evals/eval_suite.py
+forbidden_files: 
+context_files: .ai/PLAN.md, docs/vendor/antigravity-hooks-2026-10-22.md
+verify: python -m unittest tests.test_stop_hook -v
 
 ## Goal
-Implement `osr fixture-capture --cmd "<confirmed command>" --seam <id>`, make `conformance:` mandatory for seam cards that declare fixtures (or report UNVERIFIED in audit), reject seam authoritative sources in mock/test paths in task-check/plan-check, and print the Seams table during approve-plan.
+Update stop_hook.py to emit official schema adhering to docs/vendor/antigravity-hooks-2026-10-22.md, implement loop guard permitting termination after N=3 identical blocks tracked in .ai/loop_guard.json, implement PreToolUse schema conformance, and add benchmark vector V15.
 
 ## Constraints
-- Standard library only in scripts/osr.py.
-- Subprocess execution of fixture-capture must use confirmed commands or validate execution.
-- Backwards compatible for cards without seams.
+- Python 3.8+ standard library only.
+- Conformance tested against docs/vendor/antigravity-hooks-2026-10-22.md using dynamically extracted examples as fixtures.
+- Guard-allowed terminations are logged in the ledger and shown by audit/status.
+- Benchmark vector V15 includes control run and literal, disguised, and subtle variants.
 
 ## Do not
-- Do not make conformance mandatory for tasks without fixtures.
+- Do not hardcode arbitrary schema fields not defined in the vendor specification.
+- Do not reset loop-guard counter without state change or human interaction.
 
 ## Definition of done
-- Failing adversarial tests in tests/test_fixture_capture.py pass after implementation.
+- tests/test_stop_hook.py passes schema and loop-guard conformance tests.
+- Benchmark vector V15 catches stop hook contract evasion.
 - osr verify T2 passes.
diff --git a/.ai/tasks/T3.md b/.ai/tasks/T3.md
index 3273d69..b6b567f 100644
--- a/.ai/tasks/T3.md
+++ b/.ai/tasks/T3.md
@@ -1,21 +1,27 @@
-# T3: Zero-test runner output detection (V12)
+# T3: Harden quick path
 id: T3
 requirements: R3
-allowed_files: scripts/osr.py, evals/eval_suite.py, tests/test_zero_runner.py, tests/test_hardening_hypotheses.py
+depends_on: T4
+allowed_files: scripts/osr.py, tests/test_quick_hardening.py, evals/eval_suite.py
+forbidden_files: 
 context_files: .ai/PLAN.md
-verify: python -m unittest tests.test_zero_runner -v
+verify: python -m unittest tests.test_quick_hardening -v
 
 ## Goal
-Enhance `osr verify` to parse test runner outputs (unittest, pytest, jest) and fail with exit code 1 when zero tests are executed or collected, catching weak verify commands (V12).
+Harden osr quick with confirmed verify command checks, weak-command rejection, ledger-chain verification (require_chain=True), and test-config drift checks (running in verify and quick against confirm-commands fingerprints, bypassable only via secret-gated --allow-config), and add benchmark vector V16.
 
 ## Constraints
-- Standard library only in scripts/osr.py.
-- Support unittest ("Ran 0 tests"), pytest ("collected 0 items", "no tests ran"), jest ("0 passed, 0 total", "Ran 0").
+- Python 3.8+ standard library only.
+- Minimal test-config file list defined: pytest.ini, setup.cfg, tox.ini, pyproject.toml, jest.config.js, jest.config.ts, jest.config.json, vitest.config.js, vitest.config.ts, package.json [scripts block only], .eslintrc.js, .eslintrc.json, tsconfig.json.
+- Quick refuses execution during in-progress task attempts.
+- Skipped verification gates recorded explicitly in ledger and stdout.
+- Benchmark vector V16 includes control run and literal, disguised, and subtle variants.
 
 ## Do not
-- Do not fail commands that are not test runners unless they match a zero-test regex.
+- Do not allow unconfirmed or weak commands in quick.
+- Do not bypass chain integrity verification in quick.
 
 ## Definition of done
-- tests/test_zero_runner.py reproduces verify passing on zero tests initially and verifies failure after fix.
-- V12 in evals/eval_suite.py is caught.
+- tests/test_quick_hardening.py verifies quick hardening rules.
+- Benchmark vector V16 catches unconfirmed quick command and broken ledger chain.
 - osr verify T3 passes.
diff --git a/.ai/tasks/T4.md b/.ai/tasks/T4.md
index 2403b71..a78fe3a 100644
--- a/.ai/tasks/T4.md
+++ b/.ai/tasks/T4.md
@@ -1,21 +1,29 @@
-# T4: Tautological assertion detection via Python AST and JS regex (V11)
+# T4: Approval secret unreadable by agent (scrypt & terminal prompt)
 id: T4
 requirements: R4
-allowed_files: scripts/osr.py, evals/eval_suite.py, tests/test_tautological_ast.py, tests/test_hardening_hypotheses.py, tests/test_zero_runner.py
+depends_on: T4b
+allowed_files: scripts/osr.py, tests/test_approval_scrypt.py, evals/eval_suite.py
+forbidden_files: 
 context_files: .ai/PLAN.md
-verify: python -m unittest tests.test_tautological_ast -v
+verify: python -m unittest tests.test_approval_scrypt -v
 
 ## Goal
-Add Python AST checking to `osr check` detecting constant assertions (`assert 1 == 1`, `assert True`, `assertEqual(1, 1)`) and self-comparisons (`assert x == x`, `assertEqual(a, a)`), plus JS regex for `expect(x).toBe(x)`. Flag as `tautological-assertion` requiring waiver or rejection.
+Implement salted hashlib.scrypt approval secrets with interactive terminal prompt (getpass), remove --secret and OSR_APPROVAL_SECRET paths, add set-secret with password rotation rules, define sensitive flags, enforce secret checks on human commands, and add benchmark vector V17.
 
 ## Constraints
-- Standard library only in scripts/osr.py (`import ast`).
-- Safe fallback if a file cannot be parsed as Python.
+- Python 3.8+ standard library only.
+- Fail closed when no controlling TTY is present.
+- Refuse legacy unsalted SHA-256 secret in config until set-secret is rerun.
+- First set-secret happens before agent session; subsequent rotations verify old secret.
+- Audit flags any set-secret performed after plan approval.
+- Sensitive flags defined: selection flags, custom-parser exemption, --allow-config.
+- Benchmark vector V17 includes control run and literal, disguised, and subtle variants.
 
 ## Do not
-- Do not claim complete AST coverage for all languages; clearly designate non-Python checks as heuristics.
+- Do not accept plaintext or environment variable secrets.
+- Do not allow agent tools to access secret hash configurations.
 
 ## Definition of done
-- tests/test_tautological_ast.py reproduces bypass initially and verifies detection after fix.
-- V11 in evals/eval_suite.py is caught or mitigated.
+- tests/test_approval_scrypt.py tests scrypt hashing, TTY failure, rotation, and flag verification.
+- Benchmark vector V17 catches approval secret disclosure/bypass.
 - osr verify T4 passes.
diff --git a/.ai/tasks/T5.md b/.ai/tasks/T5.md
deleted file mode 100644
index a148809..0000000
--- a/.ai/tasks/T5.md
+++ /dev/null
@@ -1,21 +0,0 @@
-# T5: Out-of-band ledger anchor support and trust boundary documentation
-id: T5
-requirements: R5
-allowed_files: scripts/osr.py, SKILL.md, README.md, tests/test_anchor_ext.py
-context_files: .ai/PLAN.md, SKILL.md
-verify: python -m unittest tests.test_anchor_ext -v
-
-## Goal
-Support `--out <path>` in `osr anchor` and `--anchor <path>` in `osr ledger-verify` and `audit`. Document the exact trust boundary in SKILL.md and README: in-repo anchors do not protect against in-workspace write permissions; tamper-evidence requires out-of-band anchor storage.
-
-## Constraints
-- Standard library only.
-- Backwards compatible: defaults to `.osr-anchor` in repo root if `--out`/`--anchor` not specified.
-
-## Do not
-- Do not claim in-repo anchor is tamper-proof.
-
-## Definition of done
-- tests/test_anchor_ext.py tests out-of-band anchoring.
-- Documentation accurately reflects trust boundary.
-- osr verify T5 passes.
diff --git a/.ai/tasks/T6.md b/.ai/tasks/T6.md
deleted file mode 100644
index 6122f9c..0000000
--- a/.ai/tasks/T6.md
+++ /dev/null
@@ -1,21 +0,0 @@
-# T6: Heuristic transparency, negative test documentation, and honest CI/benchmark reporting
-id: T6
-requirements: R6
-allowed_files: scripts/osr.py, .github/workflows/test.yml, README.md, CHANGELOG.md, tests/test_honest_reporting.py
-context_files: .ai/PLAN.md, README.md
-verify: python -m unittest tests.test_honest_reporting -v
-
-## Goal
-Label heuristic checks explicitly ("heuristic: may produce false positives/negatives"), document negative-test boundaries, add Python 3.8 to .github/workflows/test.yml matrix, and update README/CHANGELOG headline metrics with honest denominators.
-
-## Constraints
-- Denominators must be honest ("X of 12 vectors caught, Y known misses").
-- CI workflow YAML must be valid.
-
-## Do not
-- Do not overclaim test coverage or vector catch rates.
-
-## Definition of done
-- tests/test_honest_reporting.py tests that heuristic output includes warnings and CI file includes 3.8.
-- README.md and CHANGELOG.md are updated.
-- osr verify T6 passes.
diff --git a/pyproject.toml b/pyproject.toml
index 7a2ffed..e2caf0a 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -4,7 +4,7 @@ build-backend = "setuptools.build_meta"
 
 [project]
 name = "orchestrator-supervisor-reviewer"
-version = "0.3.0"
+version = "0.3.1"
 description = "Deterministic verification and supervisory enforcement CLI for AI coding agents"
 readme = "README.md"
 requires-python = ">=3.8"
diff --git a/scripts/osr.py b/scripts/osr.py
index 11f5a68..2c4678e 100644
--- a/scripts/osr.py
+++ b/scripts/osr.py
@@ -583,7 +583,7 @@ def parse_plan():
             errs.append("PLAN.md: section '## %s' missing or empty" % need.title())
     reqs, cur_r = {}, None
     for ln in sections.get("requirements", []):
-        m = re.match(r"^\s*[-*]\s*(R\d+)\s*:\s*(.+)$", ln)
+        m = re.match(r"^\s*[-*]\s*(R\d+[a-zA-Z]?)\s*:\s*(.+)$", ln)
         if m:
             if m.group(1) in reqs:
                 errs.append("PLAN.md: duplicate requirement id %s" % m.group(1))
diff --git a/tests/test_osr.py b/tests/test_osr.py
index 3e0a1a0..4263cbd 100644
--- a/tests/test_osr.py
+++ b/tests/test_osr.py
@@ -130,6 +130,18 @@ class Project:
 
 
 class OsrTests(unittest.TestCase):
+    _benchmark_cache = {}
+
+    @classmethod
+    def benchmark_report(cls, version=None):
+        """Run the adversarial benchmark once per test class per version and reuse the report (read-only)."""
+        if version not in cls._benchmark_cache:
+            from evals.eval_suite import run_adversarial_benchmark
+            cls._benchmark_cache[version] = (
+                run_adversarial_benchmark() if version is None else run_adversarial_benchmark(version=version)
+            )
+        return cls._benchmark_cache[version]
+
     def setUp(self):
         self.p = Project()
         self.addCleanup(self.p.cleanup)
@@ -588,16 +600,20 @@ class OsrTests(unittest.TestCase):
     def test_adversarial_eval_suite_benchmarks_catch_rate(self):
         # Must import and run evals.eval_suite benchmark
         from evals.eval_suite import run_adversarial_benchmark
-        report = run_adversarial_benchmark()
+        report = self.benchmark_report()
         self.assertIn("catch_rate", report)
         self.assertEqual(report["catch_rate"], 1.0)
         self.assertEqual(report["false_positive_rate"], 0.0)
         self.assertGreaterEqual(report["total_cheats_tested"], 12)
-        self.assertEqual(len(report["caught_vectors"]), 10)
-        self.assertEqual(len(report["known_misses"]), 2)
+        caught_ids = {v["id"] for v in report["caught_vectors"]}
+        for required_id in ["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "V11", "V12"]:
+            self.assertIn(required_id, caught_ids)
+        v030_report = self.benchmark_report("0.3.0")
+        self.assertEqual(len(v030_report["caught_vectors"]), 10)
+        self.assertEqual(len(v030_report["known_misses"]), 2)
         self.assertIn("V9", [v["id"] for v in report["caught_vectors"]])
         self.assertIn("V10", [v["id"] for v in report["caught_vectors"]])
-        miss_ids = [m["id"] for m in report["known_misses"]]
+        miss_ids = [m["id"] for m in v030_report["known_misses"]]
         self.assertEqual(miss_ids, ["V11", "V12"])
 
     def test_seams_plan_check_warning_when_seams_table_missing(self):
@@ -1538,10 +1554,13 @@ VERDICT: PASS
 
     def test_phase6_benchmark_and_honest_reporting(self):
         from evals import eval_suite
-        report = eval_suite.run_adversarial_benchmark()
-        self.assertEqual(report["version"], "0.3.0")
+        report = self.benchmark_report()
+        import scripts.osr as osr_module
+        self.assertEqual(report["version"], osr_module.VERSION)
+        old_report = self.benchmark_report("0.3.0")
+        self.assertEqual(old_report["version"], "0.3.0")
         self.assertGreaterEqual(len(report["caught_vectors"]), 10)
-        self.assertGreaterEqual(len(report["known_misses"]), 2)
+        self.assertGreaterEqual(len(old_report["known_misses"]), 2)
         # Multi-fixture clean run measurement: at least 10 clean projects tested
         self.assertGreaterEqual(report["clean_runs_tested"], 10)
         self.assertEqual(report["false_positives"], 0)
@@ -1551,28 +1570,40 @@ VERDICT: PASS
         self.assertIn("V9", caught_ids)
         self.assertIn("V10", caught_ids)
         # Vectors V11 and V12 must be in known_misses
-        miss_ids = {v["id"] for v in report["known_misses"]}
+        self.assertIn("V11", caught_ids)
+        self.assertIn("V12", caught_ids)
+        miss_ids = {v["id"] for v in old_report["known_misses"]}
         self.assertIn("V11", miss_ids)
         self.assertIn("V12", miss_ids)
 
     def test_phase6_version_and_docs_integrity(self):
         import scripts.osr as osr_module
         # Core CLI version bump
-        self.assertEqual(osr_module.VERSION, "0.3.0")
+        import re
+        from evals import eval_suite
+        current_version = osr_module.VERSION
+        self.assertTrue(bool(re.match(r"^\d+\.\d+\.\d+$", current_version)))
         
         # pyproject.toml version
         pyproject = (ROOT_DIR / "pyproject.toml").read_text(encoding="utf-8")
-        self.assertIn('version = "0.3.0"', pyproject)
+        pyproject_ver_m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', pyproject)
+        self.assertIsNotNone(pyproject_ver_m, "pyproject.toml must declare version")
+        pyproject_ver = pyproject_ver_m.group(1)
+        self.assertEqual(current_version, pyproject_ver)
+        eval_report = self.benchmark_report()
+        self.assertEqual(current_version, eval_report["version"])
 
         # CHANGELOG.md exists and documents 0.3.0
         changelog_path = ROOT_DIR / "CHANGELOG.md"
         self.assertTrue(changelog_path.exists(), "CHANGELOG.md must exist")
         changelog = changelog_path.read_text(encoding="utf-8")
-        self.assertIn("## [0.3.0]", changelog)
+        top_changelog_m = re.search(r"##\s*\[?v?(\d+\.\d+\.\d+)\]?", changelog)
+        self.assertIsNotNone(top_changelog_m, "CHANGELOG.md must have a top version entry")
+        self.assertEqual(current_version, top_changelog_m.group(1))
 
         # README.md updates
         readme = (ROOT_DIR / "README.md").read_text(encoding="utf-8")
-        self.assertIn("0.3.0", readme)
+        self.assertIn(current_version, readme)
         self.assertIn("## Seams", readme)
         self.assertIn("## Fixtures", readme)
         self.assertIn("Enforcement setup", readme)

diff --git a/scripts/sync_skill.py b/scripts/sync_skill.py
new file mode 100644
--- /dev/null
+++ b/scripts/sync_skill.py
+#!/usr/bin/env python3
+"""
+Sync repository skill files with the global Antigravity skill directory.
+Enforces post-copy SHA-256 hash verification and supports --check mode.
+"""
+
+import sys
+import os
+import shutil
+import hashlib
+import argparse
+from pathlib import Path
+
+ROOT = Path(__file__).resolve().parent.parent
+
+SYNC_ITEMS = [
+    "SKILL.md",
+    "README.md",
+    "CHANGELOG.md",
+    "LICENSE",
+    "CONTRIBUTING.md",
+    "PROMPT-ONLY.md",
+    ".gitignore",
+    "pyproject.toml",
+    "scripts",
+    "assets",
+    "references",
+    "integrations",
+    "tests",
+    "evals",
+    "examples",
+    ".github",
+    "docs",
+]
+
+EXCLUDE_DIRS = {".git", ".ai", "__pycache__", ".pytest_cache", ".ruff_cache", "venv", ".venv"}
+EXCLUDE_EXTS = {".pyc", ".pyo", ".log"}
+
+def sha256_file(path: Path) -> str:
+    h = hashlib.sha256()
+    with open(path, "rb") as f:
+        while True:
+            chunk = f.read(65536)
+            if not chunk:
+                break
+            h.update(chunk)
+    return h.hexdigest()
+
+def get_source_files(root: Path) -> dict:
+    files = {}
+    for item in SYNC_ITEMS:
+        src = root / item
+        if not src.exists():
+            continue
+        if src.is_file():
+            rel = src.name
+            files[rel] = sha256_file(src)
+        elif src.is_dir():
+            for p in src.rglob("*"):
+                if p.is_file():
+                    # Check exclusions
+                    parts = set(p.parts)
+                    if parts & EXCLUDE_DIRS:
+                        continue
+                    if p.suffix in EXCLUDE_EXTS:
+                        continue
+                    rel = p.relative_to(root).as_posix()
+                    files[rel] = sha256_file(p)
+    return files
+
+def get_target_files(target: Path) -> dict:
+    files = {}
+    if not target.exists():
+        return files
+    for p in target.rglob("*"):
+        if p.is_file():
+            parts = set(p.parts)
+            if parts & EXCLUDE_DIRS:
+                continue
+            if p.suffix in EXCLUDE_EXTS:
+                continue
+            rel = p.relative_to(target).as_posix()
+            files[rel] = sha256_file(p)
+    return files
+
+def main():
+    parser = argparse.ArgumentParser(description="Sync skill files to target directory with hash verification.")
+    parser.add_argument("--target", default=None, help="Target skill directory path")
+    parser.add_argument("--check", action="store_true", help="Check hash parity without writing")
+    args = parser.parse_args()
+
+    if args.target:
+        target = Path(args.target).resolve()
+    else:
+        target = Path.home() / ".gemini" / "config" / "skills" / "orchestrator-supervisor-reviewer"
+
+    src_files = get_source_files(ROOT)
+
+    if args.check:
+        if not target.exists():
+            print(f"ERROR: target directory does not exist: {target}", file=sys.stderr)
+            sys.exit(1)
+        tgt_files = get_target_files(target)
+
+        missing = []
+        differing = []
+        for rel, h in src_files.items():
+            if rel not in tgt_files:
+                missing.append(rel)
+            elif tgt_files[rel] != h:
+                differing.append(rel)
+
+        extra = [rel for rel in tgt_files if rel not in src_files]
+
+        if missing or differing or extra:
+            print("Sync check failed:", file=sys.stderr)
+            for m in missing:
+                print(f"  missing: {m}", file=sys.stderr)
+            for d in differing:
+                print(f"  differs: {d}", file=sys.stderr)
+            for e in extra:
+                print(f"  extra: {e}", file=sys.stderr)
+            sys.exit(1)
+        print(f"Check OK: all {len(src_files)} files match target hashes at {target}")
+        sys.exit(0)
+
+    # Perform Sync
+    target.mkdir(parents=True, exist_ok=True)
+    synced_count = 0
+
+    for rel in src_files:
+        src_path = ROOT / rel
+        tgt_path = target / rel
+        tgt_path.parent.mkdir(parents=True, exist_ok=True)
+        shutil.copy2(src_path, tgt_path)
+        synced_count += 1
+
+    # Post-copy hash verification
+    mismatches = []
+    for rel, exp_h in src_files.items():
+        actual_h = sha256_file(target / rel)
+        if actual_h != exp_h:
+            mismatches.append(rel)
+
+    if mismatches:
+        print(f"ERROR: Post-sync hash mismatch on {len(mismatches)} files:", file=sys.stderr)
+        for m in mismatches:
+            print(f"  - {m}", file=sys.stderr)
+        sys.exit(1)
+
+    print(f"Successfully synced {synced_count} files to {target} with 100% hash parity verified.")
+
+if __name__ == "__main__":
+    main()

diff --git a/tests/test_sync_skill.py b/tests/test_sync_skill.py
new file mode 100644
--- /dev/null
+++ b/tests/test_sync_skill.py
+import os
+import sys
+import tempfile
+import unittest
+import subprocess
+from pathlib import Path
+
+ROOT = Path(__file__).resolve().parent.parent
+
+SYNCED_TOP_LEVEL = ["SKILL.md", "scripts", "assets", "references", "integrations", "tests", "evals"]
+EXCLUDED_PATTERNS = [".git", ".ai", "__pycache__"]
+
+class SyncSkillTests(unittest.TestCase):
+    def test_sync_skill_script_exists(self):
+        script_path = ROOT / "scripts" / "sync_skill.py"
+        self.assertTrue(script_path.is_file(), "scripts/sync_skill.py must exist")
+
+    def test_sync_skill_file_set_and_check(self):
+        script_path = ROOT / "scripts" / "sync_skill.py"
+        with tempfile.TemporaryDirectory() as tmp_dir:
+            target_path = Path(tmp_dir) / "target_skill"
+            
+            # 1. Run sync to copy files
+            proc = subprocess.run(
+                [sys.executable, str(script_path), "--target", str(target_path)],
+                capture_output=True,
+                text=True,
+                cwd=str(ROOT),
+            )
+            self.assertEqual(proc.returncode, 0, f"sync_skill failed: {proc.stderr}\n{proc.stdout}")
+            self.assertTrue(target_path.is_dir(), "target directory must exist")
+
+            # Check that explicit synced file set exists in target
+            for item in SYNCED_TOP_LEVEL:
+                src_item = ROOT / item
+                if src_item.exists():
+                    dest_item = target_path / item
+                    self.assertTrue(dest_item.exists(), f"Expected synced item {item} in target")
+
+            # Check that excluded patterns are NOT in target
+            for exc in EXCLUDED_PATTERNS:
+                self.assertFalse((target_path / exc).exists(), f"Excluded item {exc} should not be in target")
+
+            # 2. Run --check on identical directory, must exit 0
+            check_proc = subprocess.run(
+                [sys.executable, str(script_path), "--check", "--target", str(target_path)],
+                capture_output=True,
+                text=True,
+                cwd=str(ROOT),
+            )
+            self.assertEqual(check_proc.returncode, 0, f"sync_skill --check failed on clean sync: {check_proc.stderr}")
+
+    def test_sync_skill_negative_differing_file(self):
+        script_path = ROOT / "scripts" / "sync_skill.py"
+        with tempfile.TemporaryDirectory() as tmp_dir:
+            target_path = Path(tmp_dir) / "target_skill"
+            subprocess.run([sys.executable, str(script_path), "--target", str(target_path)], cwd=str(ROOT))
+            
+            # Tamper with file
+            tampered_file = target_path / "SKILL.md"
+            tampered_file.write_text("tampered content", encoding="utf-8")
+            
+            proc = subprocess.run(
+                [sys.executable, str(script_path), "--check", "--target", str(target_path)],
+                capture_output=True,
+                text=True,
+                cwd=str(ROOT),
+            )
+            self.assertNotEqual(proc.returncode, 0, "sync_skill --check must exit non-zero for differing file content")
+            self.assertIn("differs", proc.stderr + proc.stdout, "output should mention differing file")
+            self.assertIn("SKILL.md", proc.stderr + proc.stdout, "output must name the offending differing file")
+
+    def test_sync_skill_negative_missing_file(self):
+        script_path = ROOT / "scripts" / "sync_skill.py"
+        with tempfile.TemporaryDirectory() as tmp_dir:
+            target_path = Path(tmp_dir) / "target_skill"
+            subprocess.run([sys.executable, str(script_path), "--target", str(target_path)], cwd=str(ROOT))
+            
+            # Remove a required file
+            (target_path / "SKILL.md").unlink()
+            
+            proc = subprocess.run(
+                [sys.executable, str(script_path), "--check", "--target", str(target_path)],
+                capture_output=True,
+                text=True,
+                cwd=str(ROOT),
+            )
+            self.assertNotEqual(proc.returncode, 0, "sync_skill --check must exit non-zero when a file is missing")
+            self.assertIn("missing", (proc.stderr + proc.stdout).lower(), "output should mention missing file")
+            self.assertIn("SKILL.md", proc.stderr + proc.stdout, "output must name the offending missing file")
+
+    def test_sync_skill_negative_extra_file(self):
+        script_path = ROOT / "scripts" / "sync_skill.py"
+        with tempfile.TemporaryDirectory() as tmp_dir:
+            target_path = Path(tmp_dir) / "target_skill"
+            subprocess.run([sys.executable, str(script_path), "--target", str(target_path)], cwd=str(ROOT))
+            
+            # Add an extra file in target
+            extra_file = target_path / "extra_untracked.txt"
+            extra_file.write_text("unexpected file", encoding="utf-8")
+            
+            proc = subprocess.run(
+                [sys.executable, str(script_path), "--check", "--target", str(target_path)],
+                capture_output=True,
+                text=True,
+                cwd=str(ROOT),
+            )
+            self.assertNotEqual(proc.returncode, 0, "sync_skill --check must exit non-zero when extra file exists in target")
+            self.assertIn("extra", (proc.stderr + proc.stdout).lower(), "output should report extra file")
+            self.assertIn("extra_untracked.txt", proc.stderr + proc.stdout, "output must name the offending extra file")
+
+if __name__ == "__main__":
+    unittest.main()
```
