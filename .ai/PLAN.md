# Plan: osr v0.3 - Seams, Fixtures and Honest Verification

## Goal
Implement osr v0.3: Seams, fixtures, conditional kinds, adversarial reviews, and honest verification without breaking standard-library portability or backwards compatibility for cards without seams.

## Non-goals
- Adding paperwork or seam checks to tasks that declare no seams or kinds.
- Parsing language-specific schemas or ASTs inside osr.py (standard-library only; delegated to confirmed commands).
- Generating synthetic mock fallbacks or permitting fabricated review citations.

## Requirements
- R1: Seam inventory (plan and card level)
  - AC: Assets plan template includes Seams table, task cards support seams list, plan-check warns if external interfaces lack seams, and task-check enforces seam authoritative source in context_files.
  - Check: auto
- R2: Seam citations in reviews
  - AC: assets/quality-review.md requires a Seams section citing authoritative source snippets with @ <path>:<line> "snippet", and osr review quality verifies citations for declared seams.
  - Check: auto
- R3: Fixtures and conformance
  - AC: Task cards support fixtures, osr fixture-add tracks hashes, verify checks fixture integrity and confirmed conformance commands, and unanchored-mock flags unanchored mocks unless waived.
  - Check: auto
- R4: Conditional kinds and per-seam negative tests
  - AC: Task cards support optional kind: realtime requiring realtime review appendix, and negative_tests: enforces verified named failure tests per declared seam.
  - Check: auto
- R5: Adversarial review pack and manual path
  - AC: osr review-pack compiles diff, task card, and authoritative seam sources with adversarial verification prompt, and Check: manual paths are verified via human signoff.
  - Check: auto
- R6: Benchmark expansion, honest reporting, and v0.3.0 release
  - AC: Benchmark caught vectors include V9 and V10 alongside V1..V8, known misses are reported honestly, multi-fixture false-positive rate is evaluated, and v0.3.0 release is tagged.
  - Check: auto

## Interfaces and contracts
- Task card schema:
  - Optional `seams: <comma-separated list of seam ids>`
  - Optional `kind: realtime | api-client | persistence | ...`
  - Optional `fixtures: <comma-separated list of paths>`
  - Optional `negative_tests: <comma-separated list of test names>`
- Seams table in `PLAN.md`: `seam id | consumer | provider | authoritative source | how it is checked`
- Fixture CLI: `osr fixture-add <path> --seam <id> --source "<where captured>"`
- Quality review citation format: `@ <seam source path>:<line> "exact snippet"`

## Assumptions
- [x] Python 3.8+ standard library remains the sole runtime dependency for core `osr.py`.
- [x] Cards that declare no seams or kinds behave identically to v0.2.0.
- [x] Human operator executes human-only commands (`approve-plan`, `waive`, `unblock`, `signoff`, `reset`).

## Open questions
- None.
