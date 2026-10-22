# Plan: osr v0.3.1 Hardening

## Goal
Audit and harden osr v0.3.0 against confirmed adversarial evasion vectors (H12 hook schema contract, H1 fixture capture & mandatory conformance, H2 bogus seam source detection, H6/V12 zero-test verify detection, H5/V11 tautological assertion AST inspection, H11 out-of-band anchor support, and Phase A CI/doc truthfulness), preserving stdlib-only operation and backwards compatibility.

## Non-goals
- Parsing language-specific schemas or non-Python ASTs inside `scripts/osr.py` (standard-library only).
- Breaking existing v0.2.0 or v0.3.0 task cards that declare no seams or kinds.
- Pushing to or merging into `main` branch.

## Requirements
- R1: Antigravity stop hook contract compliance
  - AC: integrations/antigravity/stop_hook.py returns valid Antigravity Stop schema with decision and reason fields [test_stop_hook_contract]
  - Check: auto
- R2: Seam integrity, tool-captured fixtures, and mandatory conformance
  - AC: osr fixture-capture executes confirmed commands recording stdout, seam cards with fixtures mandate conformance commands or report unverified, and seam sources in test/mock paths are rejected [test_fixture_capture_and_seam_source]
  - Check: auto
- R3: Zero-test runner output detection for verify commands (V12)
  - AC: osr verify parses test runner stdout and fails with exit code 1 when zero tests are collected or executed [test_verify_zero_tests_rejected]
  - Check: auto
- R4: Tautological assertion detection via Python AST and JS regex (V11)
  - AC: osr check inspects Python AST for constant assertions and self-comparisons and flags JavaScript expect self-match regex [test_tautological_assertion_ast]
  - Check: auto
- R5: Out-of-band ledger anchor support and trust boundary documentation
  - AC: osr anchor and ledger-verify support optional external anchor file paths with documented threat model [test_external_anchor_verification]
  - Check: auto
- R6: Heuristic transparency, negative-test documentation, and honest CI/benchmark reporting
  - AC: Heuristic warnings are explicitly labeled as heuristics, CI matrix includes Python 3.8, and README/CHANGELOG report honest denominators [test_honest_reporting_and_heuristics]
  - Check: auto

## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| antigravity_hook | integrations/antigravity/stop_hook.py | Antigravity Runtime | integrations/antigravity/stop_hook.py | contract-test |
| runner_output | scripts/osr.py | Test Runners (unittest/pytest/jest) | scripts/osr.py | parser-contract-test |

## Assumptions
- [x] Python 3.8+ standard library remains the sole runtime dependency for `scripts/osr.py`.
- [x] Cards with no seams or kinds behave exactly as in v0.2.0.
- [x] The human operator approves the hardening plan and reviews independence markers.

## Open questions
- None.
