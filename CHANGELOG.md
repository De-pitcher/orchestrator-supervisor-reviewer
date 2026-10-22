# Changelog

All notable changes to `orchestrator-supervisor-reviewer` (`osr`) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-10-22

### Added
- **Stop Hook Schema Compliance (H12)**:
  - Fixed `integrations/antigravity/stop_hook.py` to match the official Antigravity Stop hook JSON schema (`{"decision": "block", "reason": "..."}`).
- **Fixture Provenance & Mandatory Conformance (H1, H2)**:
  - Added `osr fixture-capture <path> --seam <id> --cmd "<command>"` executing confirmed commands to record tool-captured fixture stdout directly.
  - Enforced that seams with fixtures without confirmed conformance runs report as `UNVERIFIED` in `osr audit` (exit code 2).
  - Added detection of bogus seam authoritative sources declared in test/mock paths.
- **Zero-Test Runner Output Detection (H6 / V12)**:
  - Added test runner stdout parsing (`run_recorded`) detecting zero-test executions (`collected 0 items`, `no tests ran`, `Ran 0 tests`) and rejecting them as weak verify commands.
  - Added `WEAK_VERIFY_PAT` in card validation rejecting token-check/grep verify commands.
- **Tautological Assertion AST Checking (H5 / V11)**:
  - Added Python AST inspection in `osr check` detecting constant assertions (`assert True`, `assertEqual(1, 1)`) and self-comparisons (`assert x == x`, `assertEqual(a, a)`).
  - Added heuristic JavaScript regex detecting self-match assertions (`expect(x).toBe(x)`).
- **Out-of-Band Ledger Anchoring (H11)**:
  - Added `--out <path>` to `osr anchor` and `--anchor <path>` to `osr ledger-verify` and `osr audit` for secure out-of-band anchor verification.
- **Heuristic Transparency & CI Matrix (H4, H7, H13, H14)**:
  - Explicitly labeled all heuristic gates (`plan-check` keyword match, `unanchored-mock`, JS regex) as heuristics in warning/flag messages.
  - Added Python 3.8 to `.github/workflows/test.yml` matrix.

### Known Limitations
- **In-Repo Trust Boundary**: In-repo anchors (`.osr-anchor`) do not protect against models with repository write access. Tamper-evident guarantees strictly require out-of-band anchor storage (`--out`).
- **Semantic Mutation Limits**: AST checks detect direct constant and self-comparison assertions, but do not replace full dynamic mutation testing (`mutmut`) for arbitrary semantic vacuity.
- **Non-Python / Non-JS Heuristics**: AST verification is implemented for Python standard library; JavaScript/TypeScript checks use regex heuristics. Other languages delegate to configured checkers.
- **Negative Test Red/Green**: `negative_tests:` verifies that named tests executed in runner output, but does not prove the test failed prior to implementation without a runner history log.

---

## [0.3.0] - 2026-10-21

### Added
- **Seams Inventory & Contracts**:
  - Added authoritative `Seams` table to `assets/PLAN.md` template (`seam id`, `consumer`, `provider`, `authoritative source`, `how it is checked`).
  - Added optional `seams:` field to task cards.
  - Added heuristic warning in `osr plan-check` when external APIs, queues, sockets, or services are declared without a Seams table.
  - Added strict `osr task-check` verification: consumer cards declaring seams must include the seam's authoritative source in `context_files` (read-only).
- **Authoritative Seam Citations in Reviews**:
  - Added `## Seams` section to `assets/quality-review.md`.
  - For every declared seam, `osr review <task> quality` verifies citations against the authoritative upstream source using `@ <authoritative-source-path>:<line> "exact snippet"`.
- **Fixtures & Contract Testing**:
  - Added `osr fixture-add <path> --seam <id> --source "<provenance>"` tracking fixture sha256, source notes, and timestamps.
  - `osr verify` enforces fixture hash integrity against registered state.
  - Added support for confirmed `conformance:` commands per seam.
  - Added `unanchored-mock` heuristic gate in `osr check` / `osr verify` to flag mocks on seam cards that do not load registered fixtures, resolvable via human waiver (`osr waive`).
  - Added `references/contract-testing.md` guide for schema-driven contracts and traffic fixtures.
- **Conditional Kinds & Negative Tests**:
  - Added optional task card `kind:` field (e.g. `kind: realtime`).
  - Added `## Realtime Appendix` in `assets/quality-review.md` enforced strictly when `kind: realtime` is declared (teardown, backpressure, race windows, time drift).
  - Added `negative_tests:` field per seam; `osr verify` / `osr done` enforces that named negative tests ran in the recorded test output.
- **Adversarial Review Pack & Honest Manual Path**:
  - Added `osr review-pack <task>` compiling diff, task card, acceptance criteria, declared seams table, and excerpted authoritative upstream sources with an adversarial verification directive prompt, stripped of builder reasoning.
  - Added `Check: manual` support with `Script:` references in `PLAN.md`; `osr audit` reports them as `PENDING-HUMAN (UNVERIFIED)` with exit code 2 until signed off via `osr signoff`.
- **Adversarial Benchmark & Clean Fixtures**:
  - Added regression test vectors V9 (`self_confirming_mock`), V10 (`seam_field_mismatch`), V11 (`tautological_assertion`), and V12 (`weak_verify_command`).
  - Vectors V1..V10 caught under active defense (100% catch rate).
  - Multi-fixture clean run measurement across 11 realistic test projects showing 0.0% false-positive rate.
  - Honest reporting separating caught active vectors from backlog known misses (V11, V12).

### Changed
- Standardized documentation and system requirements to Python 3.8+ standard library.
- Clarified that `quick` path deliberately skips review gates for rapid iteration.
- Clarified that `.osr-anchor` external ledger head must be held outside the repository for root-compromise tamper-evident guarantees.

---

## [0.2.0] - 2026-10-21

### Added
- Pluggable external language checkers configurable in `.ai/config.json`.
- Quick path verification (`osr quick`) for rapid iteration without task cards.
- External ledger anchoring (`osr anchor`) tracking append-only hash chains.
- Antigravity hooks integration (`hooks.json`, `pre_tool.py`, `stop_hook.py`).
- Git pre-commit enforcement hook (`integrations/git/pre_commit.py`).
- 8-vector adversarial regression benchmark suite in `evals/`.
- Full CLI command suite for task lifecycles, reviews, waivers, and audit trails.
