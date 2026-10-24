# Changelog

All notable changes to `orchestrator-supervisor-reviewer` (`osr`) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### CI portability follow-up — 2026-10-24
- PR #3 exposed two failures outside the original Windows/Python 3.14 run:
  Unix Git ignored the nonexecutable hook wrapper, and rapid same-size fixture
  rewrites could reuse timestamp-based Python bytecode on all platforms.
- Track the wrapper as executable and assert its Git mode and POSIX checkout
  permission. Fixture writes invalidate only the rewritten module's compiled
  cache; a deterministic equal-size/equal-timestamp regression preserves an
  unrelated cache and checks that the new source is actually imported.
- Discovery increased to **251 tests**. For commit `58a16e6`, both the
  [push matrix](https://github.com/De-pitcher/orchestrator-supervisor-reviewer/actions/runs/40043049298)
  and [PR matrix](https://github.com/De-pitcher/orchestrator-supervisor-reviewer/actions/runs/40043053441)
  passed all 15 Ubuntu/macOS/Windows × Python 3.8–3.12 jobs, with no skips.
  The earlier 249-test result below remains a historical local result.
- Synchronized skill instructions, current status, contribution/setup guides
  and guarantees with those results, exact-command/evidence rules and the
  remaining parser and trust limitations. No release or version bump is implied.

### Evidence hardening — 2026-10-23–24

Completed the T22–T27 packet against requirements R20–R25. This is an
unreleased change set; the package version remains **0.3.1**. The broader
v0.3.2 roadmap is still deferred.

### Fixed
- **T22 / R20 — retained command logs:** unique run identities, exclusive binary
  log creation, bounded collision retries, exact UTF-8 bytes and SHA-256 digests.
  Failed and timed-out commands retain output, and ledger results identify each
  command's own log.
- **T23 / R21 — command authorization:** require an exact confirmed command
  after trimming outer whitespace. Arguments, quoting, internal whitespace and
  shell suffixes no longer inherit executable-wide permission. Failed
  reconfirmation revokes earlier success; quick verification and fixture capture
  reject stale approval/configuration and unauthorized execution.
- **T24 / R22 — current test evidence:** stop scanning historical XML reports;
  validate retained-log hashes and exclude failed commands. Match canonical
  identities exactly, preserve pytest parameters and reject missing or ambiguous
  short declarations. Acceptance tags retain nested brackets rather than
  silently dropping declarations.
- **T25 / R23 — completion freshness:** bind approval baselines, task starts,
  verification, reviews and completed deltas to governed content. Reject
  pre-start drift, mid-verification writes, stale cards, conflicting records and
  interrupted persistence. Replay accepted overlapping deltas, support cold
  replay without snapshot caches and revalidate state at lock boundaries.
  Genuine legacy closures remain explicitly UNVERIFIED without current credit.
- **T26 / R24 — staged artifact checks:** use read-only `audit --check` and
  complete governed-index comparison, including required governance evidence.
  Reject partial staging, stale/index-only content, unsupported transformations
  and governance aliases. Preserve worktree cwd in both documented wrapper
  layouts. Identical supported binary bytes pass; only Git-recognized text
  permits narrowly defined CRLF/LF equivalence.

### Changed
- **T27 / R25 — integration:** migrated fixtures to real approval lineage and
  exact command confirmation without removing tests or weakening rejection
  assertions. Bootstrap fixtures preserve caller files and introduce new
  behavior after task start. Benchmark consumers share one captured report.
- Corrected documentation about actor labels, optional approval secrets,
  external anchors, hook bypasses, governed-file coverage and parser limits.
- Preserved superseded plans, cards, snapshots and ledger history. Approval
  epoch 298 establishes the new baseline; historical completions are disclosed
  without supplying current requirement credit.

### Carried-forward baseline work
- Retained package metadata alignment to 0.3.1, sub-requirement ID parsing,
  benchmark caching/version-test repairs, the skill synchronization utility and
  its tests, and the manual terminal assessment script. These preceded the
  evidence-hardening implementation and were included in its approved baseline.

### Validation record
- Independent supervisor spec and quality reviews accepted T27; it closed at
  ledger sequence **325**, following formal verification at **322**.
- The final integration inventory contains **249 distinct tests**: 171 in five
  formal focused modules and 78 in eight supplementary batches. Every ID ran
  exactly once in that schedule; all passed on one unchanged governed tree.
- The single final benchmark execution caught **12/12 attacks**, with **11 clean
  canaries and zero false positives**. Final acceptance audit verified R20–R25
  and ledger integrity. These are local results, not remote CI results.
- Source records: [independent evidence](.ai/reviews/T27.final-evidence.supervisor/independent-audit.json),
  [batch inventory and results](.ai/reviews/T27.final-evidence.supervisor/run-summary.json),
  and [acceptance audit](.ai/AUDIT.md). Historical release dates below follow
  local Git history; existing release entries describe their state at release.

### Known limitations and deferred work
- Validation used Windows and Python 3.14.3. Native Linux/macOS, other Python
  versions and remote CI were not verified by this packet.
- Standard verbose unittest output with method docstrings can split identity and
  status across lines. The current parser conservatively omits those named
  identities: 171 formal tests executed, while 148 canonical IDs were recorded.
  Multiline parser support is deferred.
- Git hooks remain bypassable with `--no-verify`; `allow_no_commands` remains an
  explicit compatibility escape. Neither is a security boundary.
- `--by` is self-reported, the approval secret is optional, and harness hooks do
  not authenticate actors. An external anchor only protects its pinned ledger
  prefix when independently compared; it does not establish truth of later
  entries or protect tooling writable by the same actor.
- XML-only runner discovery, actor-authentication redesign and broader v0.3.2
  release features remain deferred. No publication or version bump is implied.

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

---

## [0.1.0] - 2026-10-21

### Added
- Initial Orchestrator, Supervisor, Reviewer skill and standard-library Python
  CLI: task cards, scoped changes, verification, spec/quality review, completion,
  failure triage and requirement audits backed by a hash-chained ledger.
- Skill instructions, task/review templates and reference guides establishing
  the principle that command evidence, rather than an agent's assertion,
  determines completion.

Historical source: initial release commit `b00e5cd`. Subsequent roadmap phases
are summarized under 0.2.0 and 0.3.0; v0.3.1 hardening is commit `769b307`.
