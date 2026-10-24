# Plan: osr v0.3.2 Hardening & Bypass Mitigation

## Goal
Close the verification bypasses identified during the v0.3.1 implementation audit across the MUST tier (Phases 0 through 5): repair the test baseline and sync global skill copy (R0), introduce explicit evidence classes in the ledger and audit (R1), implement official Antigravity Stop hook schema with loop guard and PreToolUse contract (R2), harden `osr quick` with command confirmation, chain verification, and test-config protections (R3), replace readable approval secrets with salted scrypt interactive terminal prompts failing closed without TTY (R4), empirically verify agent terminal interactive prompt behavior (R4b), and enforce test-run integrity with positive counts, new test execution verification, assertionless test scanning, and selection flag controls across verify and quick (R5a, R5b).

## Non-goals
- Parsing non-Python ASTs or language-specific schemas inside `scripts/osr.py` (standard-library only).
- Breaking backwards compatibility for existing cards without new optional fields.
- Pushing to or merging into `main` branch.
- Weakening existing test assertions or benchmark vectors (no test removed, assertion counts not reduced).

## Task Order
1. R0: Repair test suite baseline & sync global skill copy
2. R1: Evidence classes in the ledger and audit
3. R2: Stop hook correctness and loop guard
4. R4b: Antigravity agent terminal interactive prompt assessment (manual signoff)
5. R4: Approval secret unreadable by agent (scrypt & terminal prompt)
6. R3: Harden quick path
7. R5a: Positive test counts and new test execution
8. R5b: Assertionless tests, selection flags, and extra tautologies

## Requirements
- R0: Repair test suite baseline & sync global skill copy
  - AC: Fix the 3 failing tests in tests/test_osr.py by asserting version consistency across the project (osr.VERSION == pyproject version == eval_suite version == top CHANGELOG entry) and asserting benchmark results per required vector ID without hardcoded counts and without weakening (no test removed, assertion counts not reduced) [test_baseline_repair_green]
  - AC: Execute a confirmed global_verify command validating the full test suite is green with pass count recorded in ledger and status [test_full_suite_confirmed_global_verify]
  - AC: Implement scripts/sync_skill.py supporting --check --target <path> which exits 0 only when all destination file hashes match source, with a temp-dir test and no usernames or absolute paths in plan or config [test_sync_skill_script_and_hash_comparison]
  - Check: auto

- R1: Evidence classes in the ledger and audit
  - AC: Ledger check entries record explicit evidence class with no default class (any entry type without a declared class fails tests and audit); re-justified classification: observed (direct execution outcome: verify exit code, quick exit code, seam conformance execution exit code, fixture capture exit code), heuristic (static approximation or unverified output: stdout-parsed positive test counts, scope lock check, placeholder pattern scan, reference integrity check, tautological assertion AST/regex scan, assertionless test scan, unapproved selection flag scan), or attested (human declarations: approve-plan human approval, signoff manual requirement signoff [retaining HUMAN-SIGNED status], waive check flag waiver, reset human task reset) [test_ledger_evidence_classes_recorded]
  - AC: Audit requirement traceability table displays evidence classes present per requirement, and VERIFIED status strictly requires >=1 observed entry (failing down to HEURISTIC-ONLY or ATTESTED-ONLY otherwise); legacy unclassified ledger entries produce UNCLASSIFIED-LEGACY with exit code 2 (no auto-classification) [test_audit_weakest_evidence_class]
  - AC: A task counts toward a requirement only if its done entry is newer than the current plan approval and the card's recorded input hash matches the current card; otherwise the task is STALE and audit exits non-zero. [test_audit_ignores_stale_task_state]
  - AC: osr ledger-verify verifies hash-chain integrity on legacy v0.3.1 ledger fixtures without errors [test_ledger_verify_v031_backwards_compatible]
  - AC: Benchmark vector V14 (with control run passing cleanly, literal, disguised, subtle and task-id-reuse variants failing on v0.3.1 and passing on v0.3.2; the task-id-reuse variant reuses an old done task id for a new card) catches unclassified or disguised heuristic evidence with gate id gate_evidence_classes [test_vector_v14_evidence_classes_gate]
  - Check: auto

- R2: Stop hook correctness and loop guard
  - AC: Stop hook emits official schema (decision and reason) conforming to captured vendor contract docs/vendor/antigravity-hooks-2026-10-22.md, with stop-hook tests dynamically extracting examples from the vendor doc at test time as test fixtures [test_stop_hook_contract_schema]
  - AC: Stop hook inspects osr status --json and allows termination after N=3 consecutive identical blocks tracked in loop-guard counter file .ai/loop_guard.json, or when human action is pending; guard-allowed terminations are logged in the ledger and displayed in audit and status [test_stop_hook_loop_guard_n3]
  - AC: PreToolUse hook conforms to the schema in the vendor doc (docs/vendor/antigravity-hooks-2026-10-22.md), blocking protected path modifications and dangerous commands [test_pre_tool_use_schema_conformance]
  - AC: Benchmark vector V15 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches stop hook contract evasion with gate id gate_stop_hook_contract [test_vector_v15_stop_hook_gate]
  - Check: auto

- R4b: Antigravity agent terminal interactive prompt assessment
  - AC: Attempt to run approve-plan from the real Antigravity agent terminal, document whether it can answer an interactive prompt or fails closed without TTY, apply the decision rule (if the agent terminal can answer prompts, document no protection in that harness, recommend separate OS user or CI-only approvals, and open a follow-up issue), and record manual human signoff [manual_agent_terminal_tty_signoff]
  - Check: manual
  - Script: scripts/test_agent_tty.py

- R4: Approval secret unreadable by agent (scrypt & terminal prompt)
  - AC: Define sensitive flags (selection flags, custom-parser exemption, --allow-config); any waiver or bypass of sensitive flags requires human authorization with secret verification recorded in the ledger [test_sensitive_flags_governance]
  - AC: Implement set-secret command prompting for password with confirmation, generating salted hashlib.scrypt hash, and writing an attested ledger entry containing the secret hash fingerprint; first set happens before any agent session; any subsequent set-secret requires verifying the old secret; audit flags any set-secret performed after plan approval [test_cmd_set_secret_rotation_and_audit_flag]
  - AC: Every human-only command (approve-plan, unblock, reset, signoff, waive for sensitive flags) prompts for the secret and verifies the computed hash matches the last fingerprint recorded in the ledger [test_human_commands_verify_secret_fingerprint]
  - AC: Approval commands fail closed with explicit error when no controlling TTY/console is present [test_approval_fail_closed_no_tty]
  - AC: Refuse legacy unsalted SHA-256 secret in config until set-secret command is rerun [test_approval_refuse_legacy_unsalted]
  - AC: Remove --secret CLI flag and OSR_APPROVAL_SECRET environment variable from approval commands to prevent process-table or environment snooping [test_approval_secret_scrypt_terminal]
  - AC: Audit records unprotected approvals with prominent warning [test_audit_records_unprotected_approvals]
  - AC: PreToolUse deny rules prevent agent tool calls from inspecting or modifying approval secret files [test_pre_tool_deny_secret_access]
  - AC: Benchmark vector V17 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches approval secret disclosure/bypass with gate id gate_approval_scrypt_terminal [test_vector_v17_approval_secret_gate]
  - Check: auto

- R3: Harden quick path
  - AC: Define minimal test-config file list (pytest.ini, setup.cfg, tox.ini, pyproject.toml, jest.config.js, jest.config.ts, jest.config.json, vitest.config.js, vitest.config.ts, package.json [scripts block only], .eslintrc.js, .eslintrc.json, tsconfig.json) [test_test_config_file_list_defined]
  - AC: Test-config drift check runs in both osr verify and osr quick against fingerprints recorded at confirm-commands (not uncommitted changes) and refuses execution unless bypassed by --allow-config (which requires the approval secret and records an attested ledger entry) [test_config_drift_check_verify_and_quick]
  - AC: osr quick requires confirmed verify commands matching .ai/config.json and rejects unconfirmed commands [test_quick_requires_confirmed_verify]
  - AC: osr quick rejects trivial commands and weak verify patterns (token existence checks) [test_quick_rejects_weak_commands]
  - AC: osr quick enforces ledger hash-chain integrity verification (require_chain=True) [test_quick_enforces_ledger_chain]
  - AC: osr quick refuses execution during in-progress task attempts [test_quick_refuses_during_in_progress_tasks]
  - AC: osr quick records skipped verification gates explicitly in ledger entry and stdout output [test_quick_records_skipped_gates]
  - AC: Benchmark vector V16 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches unconfirmed quick command and broken ledger chain with gate id gate_quick_confirmation_and_chain [test_vector_v16_quick_path_gate]
  - Check: auto

- R5a: Positive test counts and new test execution
  - AC: Record base commit hash at osr start; newly added or modified test functions are determined via git diff against base_commit (falling back to stored copies saved at osr start, else marking UNVERIFIED) [test_record_base_commit_and_diff]
  - AC: Parse positive test execution counts from runner output captured via fixture-capture from real test runs; unittest and pytest are verified against captured seam sources; jest and vitest are experimental notes with no declared seam (producing UNVERIFIED unless exempted by a human-approved osr waive for sensitive flags recorded in the ledger) [test_runner_positive_counts_in_scope]
  - AC: Verify newly added or modified test function names appear in runner output; runners are invoked with standard environment variables LC_ALL=C and PYTHONIOENCODING=utf-8, preferring locale-independent parsers; non-English or unparseable runner output produces UNVERIFIED status [test_new_tests_executed_and_locale_handling]
  - AC: When test runner output contains no individual test names (non-verbose runner execution), verify command flags missing test names and requires verbose flag or marks UNVERIFIED with actionable warning [test_runner_non_verbose_warning]
  - AC: Benchmark vector V18 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches zero-test and unparsed runner outputs with gate id gate_runner_positive_counts [test_vector_v18_runner_counts_gate]
  - Check: auto

- R5b: Assertionless tests, selection flags, and extra tautologies
  - AC: Check scans test diffs and flags assertionless test functions via AST (Python) and regex (JS/TS), tested against literal (test_assertionless_literal), disguised (test_assertionless_disguised), and subtle (test_assertionless_subtle) evasion patterns [test_assertionless_detection]
  - AC: Check rejects unapproved test runner selection flags in verify commands (-k, -m, -t, --testNamePattern, test path filters) unless exempted by a human-approved osr waive for sensitive flags recorded in the ledger (not a task card field), tested with literal (test_selection_flags_literal), disguised (test_selection_flags_disguised), and subtle (test_selection_flags_subtle) variants [test_selection_flags_detection]
  - AC: Check inspects extended tautological assertions (assert True, self == self, expect(x).toBe(x), Boolean literals, tautological boolean expressions), tested with literal (test_tautology_literal), disguised (test_tautology_disguised), and subtle (test_tautology_subtle) variants [test_tautology_extended_detection]
  - AC: Integrity checks (assertionless tests, selection flags, tautologies) are wired into both osr verify and osr quick [test_integrity_checks_wired_verify_and_quick]
  - AC: Benchmark vector V19 (with control run passing cleanly and literal, disguised, subtle variants failing on v0.3.1 and passing on v0.3.2) catches assertionless tests and evasion variants with gate id gate_assertionless_and_tautology_scan [test_vector_v19_assertionless_gate]
  - Check: auto

## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| antigravity_hook | integrations/antigravity/stop_hook.py | Antigravity Runtime | docs/vendor/antigravity-hooks-2026-10-22.md | contract-test: python -m unittest tests/test_stop_hook.py |
| runner_output_unittest | scripts/osr.py | unittest Runner | docs/vendor/runner_outputs/unittest_output.txt | parser-conformance-test: python -m unittest tests/test_runner_parsers.py |
| runner_output_pytest | scripts/osr.py | pytest Runner | docs/vendor/runner_outputs/pytest_output.txt | parser-conformance-test: python -m unittest tests/test_runner_parsers.py |

## Assumptions
- [x] Python 3.8+ standard library remains the sole runtime dependency for `scripts/osr.py`.
- [x] All new fields and flags are optional; existing projects without them behave as in v0.3.1.
- [x] Antigravity Stop and PreToolUse hook specifications and examples are anchored to captured vendor documentation `docs/vendor/antigravity-hooks-2026-10-22.md`.
- [x] Loop-guard counter is persisted across hook invocations in `.ai/loop_guard.json`.
- [x] Vector suite does not contain V13; V13 is reserved and new vectors continue sequentially as V14 through V19.
- [x] Benchmark vectors V14 through V19 require control runs (cheat removed passes) and must fail on v0.3.1 baseline and pass on v0.3.2.
- [x] Jest and Vitest runners are experimental notes with no declared seam; unittest and pytest are the sole active runner output seams.

## Open questions
- OQ1 (OPEN - pending R4b manual signoff): Does the Antigravity agent terminal allow interactive getpass input, or will approve-plan fail closed when run non-interactively? (Evaluated via scripts/test_agent_tty.py and documented in .ai/TTY_ANALYSIS.md; kept open until human signoff in R4b).
- [x] OQ2: How should test runners not installed locally (e.g. Jest/Vitest) be validated in CI without adding heavyweight npm dependencies? (Resolved: unittest and pytest are the sole in-scope seams verified via fixture-capture from real runs; jest and vitest are experimental notes with no seam and produce UNVERIFIED unless waived).
- [x] OQ3: How are localized test runner outputs handled if a non-English OS environment runs tests? (Resolved: Test runners are invoked with standard environment variables LC_ALL=C and PYTHONIOENCODING=utf-8, and regex parsers prefer locale-independent patterns; non-English output is marked UNVERIFIED).
