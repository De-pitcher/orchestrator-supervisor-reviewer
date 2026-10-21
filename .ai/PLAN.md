# Plan: osr Improvement Roadmap (Antigravity + Gemini)

## Goal
Evolve orchestrator-supervisor-reviewer into a production-grade, packaged, tamper-resistant supervisory harness with Antigravity integration, pluggable checkers, and an adversarial evaluation suite, governed strictly by its own deterministic enforcement loop.

## Non-goals
- Replacing the standard library foundation of the core CLI with heavy third-party runtime dependencies.
- Permitting unverified model claims, self-approved plans, or synthetic mock shortcuts in place of real command evidence.
- Full Windows sandboxing prior to upstream platform availability (relying instead on strict deny rules and CI verification).

## Requirements
- R1: Quick wins, modular refactoring, and packaging
  - AC: osr provides deterministic --json output, stable exit codes, a pyproject entry point for pipx, a ledger lock file, and a modular architecture without breaking existing tests.
  - Check: auto
- R2: Red/Green evidence enforcement and cheat rejection
  - AC: osr start captures a test state baseline; verify requires changed tests to fail before and pass after; and cheat attempts like verify: true or loosened assertions are rejected.
  - Check: auto
- R3: Requirement-to-test-to-run traceability matrix
  - AC: Acceptance criteria map to test IDs, verify parses JUnit or test runner JSON, and audit blocks task completion if criteria tests did not run and pass.
  - Check: auto
- R4: Tamper-resistant trust model and approval tokens
  - AC: Human approvals require an external secret, config changes invalidate plan approval, and osr anchor commits ledger state externally for verification.
  - Check: auto
- R5: Antigravity workspace integration and enforcement hooks
  - AC: Antigravity workspace hooks.json and permissions engine enforce allowed_files scope limits, hard-block agent execution of approve-plan, and gate done on osr next.
  - Check: auto
- R6: Reviewer bundle packaging and quick path mode
  - AC: osr review-pack bundles only diff, task card, and criteria without builder explanations, and osr quick enables rapid single-command verification for small fixes.
  - Check: auto
- R7: Pluggable checkers and adversarial evaluation benchmark
  - AC: config.json supports external language checkers and the adversarial test suite benchmarks catch rate and false-positive rate across seeded cheats.
  - Check: auto

## Interfaces and contracts
- CLI JSON output schema: `{"status": "ok"|"error"|"blocked", "phase": "<phase>", "task": "<id>", "evidence": {...}, "next": "<command>"}`.
- Exit code specification: `0` (Success/Pass), `1` (User/Command syntax error), `2` (Gate verification failure), `3` (Triage required/Blocked), `4` (Ledger/Config tampering).
- Ledger lock: `.ai/.ledger.lock` using atomic file creation / standard locking.

## Assumptions
- [x] Python 3.8+ standard library remains the sole runtime dependency for core `osr` CLI.
- [x] Initial Phase 0 baseline test suite is 100% green on Windows and CI matrix.
- [x] Human operator executes human-only commands (`approve-plan`, `unblock`, `signoff`, `reset`).

## Open questions
- None. All phase definitions and scope boundaries from the roadmap are accepted.
