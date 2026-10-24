# osr v0.3 Roadmap: Seams, Fixtures and Honest Verification

> **Historical planning document.** This records the v0.3 design and its original proposed phases; it is not the current feature/status contract. See [README.md](README.md) for current behavior and validation, [CHANGELOG.md](CHANGELOG.md) for completed history, and the [preserved v0.3.2 proposal](docs/planning/v0.3.2-proposal/README.md) for deferred work. The original proposal below is retained for provenance.

Repo: https://github.com/De-pitcher/orchestrator-supervisor-reviewer

Origin: a real-use audit on a multi-repo project found four classes of bug that v0.2.0 passed as green:
1. Self-confirming mocks (the builder wrote the code and the mock, both on the same wrong assumption).
2. Cross-repo seam blindness (the builder never saw the backend's real field names).
3. Protocol and timing behavior (close codes, backpressure, drain windows) invisible to unit tests.
4. A same-model reviewer who asked the same generic questions as the builder.

Principle for this release: **do not add paperwork to every task. Add checks that trigger only when a card declares a seam or a kind.**

---

## How to run this roadmap (Antigravity)

- **Dogfood.** Each phase is: plan, task cards, `osr verify`, reviews. Use osr to build osr.
- **One phase per session.** Give the model only that phase's goal, the files it may touch and its acceptance criteria.
- **Tests first.** The model writes failing tests (including cheat attempts) first. You approve them. Then it implements.
- **Independent review.** Phases 2, 3 and 5 change what counts as evidence. Have a different model review their diffs.
- **Keep the stdlib-only rule.** `osr.py` must not parse TypeScript or any language-specific schema. Language-specific checking is delegated to a confirmed command that the user supplies.
- **Check the existing hooks** (Antigravity `hooks.json`, pre-commit) still work after each phase.

---

## Phase 0: Baseline and failing benchmark vectors

Goal: turn the audit into regression tests that fail first.

- Run the full test suite and the benchmark on your OS. Record the results.
- Create a branch and put this roadmap into `.ai/PLAN.md` as requirements R1..Rn with acceptance criteria.
- Add benchmark vectors to `evals/` that the current version is expected to MISS:
  - **V9 `self_confirming_mock`:** a test whose mock returns fields that do not exist in the declared upstream source, and the code reads those fields.
  - **V10 `seam_field_mismatch`:** a consumer card whose seam source is not in `context_files`.
  - **V11 `tautological_assertion`:** `assert 1 == 1` replacing a real assertion.
  - **V12 `weak_verify_command`:** `verify: pytest -k nothing_matches` or a `grep` that always succeeds.
- Mark them `known_miss` in the report for now. The report must show caught and missed vectors separately.

**Done when:** the benchmark reports V1..V8 caught and V9..V12 as known misses, and the tests are green.

---

## Phase 1: Seam inventory (plan and card level)

Goal: every cross-boundary interface is declared, with its authoritative source.

- Add a **Seams** table to the `assets/PLAN.md` template: `seam id | consumer | provider | authoritative source (path or URL or schema file) | how it is checked`.
- Add optional `seams:` to the task card (list of seam ids the card consumes or provides).
- `plan-check`: warn if a requirement mentions an external API, service, queue or socket but the Seams table is empty. This is a heuristic, so warn, do not block.
- `task-check`: for every seam on a card, the seam's authoritative source must appear in `context_files` (read-only), or the card fails. Do not add a new `context_contracts` field.
- Clarify in SKILL.md: Rule 5 limits edits only. Reading provider code via `context_files` is allowed and expected.

**Done when:** a consumer card whose seam source is missing from `context_files` fails `task-check` (V10 is now caught), and cards with no `seams:` behave exactly as before.

---

## Phase 2: Seam citations in reviews

Goal: the reviewer must open the upstream definition and cite it, using the existing snippet checker.

- Add a **Seams** section to `assets/quality-review.md`. For each declared seam, the reviewer lists every external field or call the code uses, each cited as `@ <seam source path>:<line> "exact snippet"` pointing into the authoritative source.
- `osr review <task> quality` must verify these citations the same way it already verifies `file:line "snippet"`, and require at least one per declared seam.
- Cards with no seams: section is not required.

**Done when:** a quality review that cites only consumer files for a declared seam is rejected, and a correct one passes.

---

## Phase 3: Fixtures and conformance

Goal: replace fabricated mocks with recorded fixtures, and verify them with a user-supplied checker.

- Card field `fixtures:` listing fixture files for each seam. Add `osr fixture-add <path> --seam <id> --source "<where captured>"`, which records the file's sha256, source note and date. It does NOT fetch anything.
- `verify` fails if a registered fixture's hash changed without being re-registered.
- Per seam, optional `conformance:` command (for example `tsc --noEmit`, an ajv or zod validation script, or a generated-client check). It must be in the confirmed command list and pass.
- Heuristic gate `unanchored-mock`: detect common mock constructs in changed test files (`jest.mock`, `vi.mock`, `msw`, `nock`, `unittest.mock`, `responses`, inline JSON response literals) on a card that declares seams. Flag unless the mock loads a registered fixture. Resolution is a waiver (human-approved). Document this as a heuristic, not a guarantee.
- Add `references/contract-testing.md`: generate consumer types from the provider's schema (OpenAPI, protobuf, shared package) so field mismatches fail compilation; capture fixtures from real traffic; never let the builder invent response shapes.

**Done when:** V9 is caught (mock without anchor flagged), a card with a registered fixture and a passing conformance command verifies cleanly, and a modified fixture fails verify.

---

## Phase 4: Conditional kinds and per-seam negative tests

Goal: lifecycle and failure-path checks only where they apply.

- Optional card field `kind:` (for example `realtime`, `api-client`, `persistence`).
- Add an appendix to `assets/quality-review.md` shown only for `kind: realtime`:
  - Teardown: which close codes or signals are sent, and does reconnect distinguish user-intentional stop from failure?
  - Backpressure: can a burst saturate network or memory buffers, and are there asynchronous yields?
  - Race windows: what happens if an event arrives while a prior socket or transaction is draining?
  - Time drift: do metrics accumulate real deltas or flat increments?
- Card field `negative_tests:` with one named test per declared seam covering unexpected or missing upstream fields. `verify` checks that each named test appears in the recorded test output. State clearly in the docs that this proves the test ran, not that it is meaningful.
- If red/green evidence (baseline fails, then passes) already exists in the codebase, require it for negative tests. If it does not, record it under "Not yet" in the README.

**Done when:** a `kind: realtime` card requires the appendix, other cards do not, and a missing named negative test blocks `done`.

---

## Phase 5: Adversarial review pack and manual path

Goal: independent review that checks the upstream truth, and honest handling of what cannot be automated.

- `review-pack` includes: the diff, the card, the acceptance criteria, the seam table and the excerpted authoritative sources, and an adversarial prompt: "For every external field, find its definition in the provided source. Report any field the code uses that the source does not declare. Do not trust the builder's explanation."
- Requirements that cannot be machine-checked (wire timing, real-server behavior) get `Check: manual` with a manual test script file referenced in the plan. `audit` shows them as UNVERIFIED until `signoff`.
- Document the recommended practice: test realtime code against a real local server (for example a real WebSocket server) and not an in-memory mock.

**Done when:** the review pack contains no builder reasoning, and an unsigned manual requirement keeps `audit` at exit code 2.

---

## Phase 6: Benchmark, docs and release

- Re-run the benchmark. V9 and V10 should now be caught. V11 and V12 may remain known misses unless mitigated. Report caught and missed together, honestly.
- Replace the false-positive "0/1" with a real sample: run clean tasks across several fixture projects (at least 10) and report the actual rate.
- Update the README:
  - Add the Seams, Fixtures and `kind` features to Quick start and the command table.
  - Add an **Enforcement setup** section (Antigravity hooks, pre-commit, CI, anchor) with install steps.
  - Fix inconsistencies: Python version claim (3.8+ vs 3.9+), the "What you get" tree (add `evals/`, integrations), and link a green CI run for the platform claim.
  - Add a **Not yet** list for anything from the roadmaps that is still unbuilt.
  - State that `quick` skips review gates.
  - Say where `anchor` writes the ledger head and who must hold it for the guarantee to hold.
- Add CHANGELOG.md. Bump to v0.3.0. Tag the release. Confirm the push reached GitHub.

**Done when:** the README numbers come from a reproducible run, CI is green on all platforms, and the tag exists.

---

## Prompt template for each Antigravity session

```
Phase N of the roadmap in .ai/PLAN.md.
Goal: [one sentence].
You may touch only: [files].

Constraints:
- osr.py stays standard-library only; do not parse language-specific schemas.
- Cards that declare no seams or kinds must behave exactly as before.
- Heuristic checks must warn or require a human waiver, never claim certainty.

First write failing tests for each acceptance criterion, including attempts
to cheat the gate, and stop for my approval. Then implement.
Do not change behavior outside this phase.
Run the full test suite and the benchmark and show me the output.
List anything you were unsure about instead of guessing.
```

---

## Risks

- **Heuristic mock detection will false-positive on legitimate mocks.** Keep the waiver path painless (`osr waive <task> unanchored-mock --reason "..."`).
- **Review citations are tedious.** The command must print the exact format expected and point to the line numbers.
- **Fixture staleness.** A fixture passes today but the backend changes tomorrow. This is why the authoritative source is also tracked and cited.
- **Realtime servers in CI.** A WebSocket test server can be flaky if ports collide. Recommend ephemeral ports (`port: 0`).
