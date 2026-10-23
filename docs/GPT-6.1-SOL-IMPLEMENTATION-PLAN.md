# OSR v0.3.2 implementation handoff for GPT-6.1-sol

Prepared: 2026-10-23. Status: proposed execution plan, not an approved OSR plan.

This document translates the repository analysis into bounded implementation sessions. It does not approve `.ai/PLAN.md`, change task state, authorize a release, or record completion. Model choice is the user's requested GPT-6.1-sol; the instructions below are ordinary repository handoffs, not claims about model pricing or special capabilities.

## 1. Outcome and starting point

Deliver v0.3.2 with evidence tied to the actual plan, task inputs, code and command attempt; bounded hooks; defensible approval handling; and honest reporting of heuristic and manual evidence.

Observed baseline on 2026-10-23:

- Branch `v0.3.2`; HEAD `769b307`; runtime and package version `0.3.1`.
- Working tree contains existing uncommitted changes. Preserve them and identify ownership before editing.
- `python -m unittest discover -s tests -v`: 78 tests passed in 270.972 seconds on Windows/Python 3.14.3. This is a historical local observation, not a new run or proof of remote CI.
- Benchmark tests asserted V1-V12 caught and zero false positives in the existing synthetic sample.
- `ledger-verify`, `plan-check` and all current card validations passed.
- Plan approval is voided. T0 is in progress; T10-T16 are todo.
- Installed-skill check differed in `scripts/sync_skill.py`, `tests/test_osr.py`, and `tests/test_sync_skill.py`.
- Some green hardening tests intentionally demonstrate remaining vulnerabilities. They must not be described as proof that those vulnerabilities are fixed.

Do not restart the project, recreate the ledger, discard work, reuse archived task IDs, or implement the old v0.3.0 roadmap again.

## 2. Session protocol and token discipline

Use one builder session per packet, with GPT-6.1-sol selected in the host application. Do not build a model-calling wrapper or spawn agents just to execute this plan.

Each session reads:

1. Applicable repository instructions and `SKILL.md` once per fresh session.
2. `python scripts/osr.py next` and the current card.
3. The relevant requirement and packet from this document.
4. Only the source functions, tests and authoritative context needed for that packet.
5. The previous packet's short handoff if it affects the current task.

Use `rg -n` to locate functions, then read bounded ranges. Do not repeatedly dump the entire CLI, historical audit reports, ledger or all task cards. Read more when necessary to understand callers and security implications; context limits must not become an excuse for guessing.

During development, run focused tests. At formal verification, run the confirmed commands required by OSR, including configured global verification. Do not weaken or remove global verification to save tokens. Reuse one unchanged successful benchmark result within a test process; avoid launching a duplicate standalone benchmark immediately after the same benchmark has run in the full suite.

Keep full command output in captured logs and report exit code, test count, failures and log path. Print failure details when present. Never reconstruct command output from memory or a handoff.

Separate builder and reviewer sessions. A fresh reviewer session can use GPT-6.1-sol too, but that is still the same model; do not invent a different model identity to satisfy `require_distinct_reviewer`. If distinct-model review is required by the approved plan, use a genuinely different reviewer or obtain a real plan decision.

### Required handoff, at most 250 words

```text
Task and state:
Files changed:
Behavior implemented:
Checks actually run: command, exit, count, log path
Review/closure status:
Remaining failures or limitations:
Next required action:
```

Write handoffs only to a location explicitly permitted by the card, such as `.ai/handoffs/Tn.md`. Use transcripts if no such location is permitted. Generated governance files remain tool-managed; never manually edit state or ledger entries.

## 3. Planning reconciliation before feature code

This is the first session. Its output is revised planning artifacts for human review, not implementation.

Allowed proposed planning files: `.ai/PLAN.md`, current `.ai/tasks/T0.md` and `T10.md` through `T16.md`, new cards listed below, and a short decision record. Do not edit production code or mark tasks done.

Read `.ai/T0-DEVIATIONS.md` before touching baseline requirements. Preserve the documented prior decisions about assertion updates and the sync file set.

Prepare these changes together so the human reviews one coherent plan:

1. Preserve IDs T0 and T10-T16. Check that proposed T17-T21 are unused before adding them; choose fresh IDs if necessary.
2. Move normalized positive test-count storage from R0 into R5a/T15. T0 will require captured full-suite output and exit evidence; it will not depend on an unbuilt parser. This changes acceptance criteria and requires explicit human approval.
3. Replace R0's nonexistent acceptance-test tags with existing precise test names, or add meaningful named tests. Do not add wrappers that merely satisfy a name check.
4. Expand T11's scope to include `scripts/osr.py`, `integrations/antigravity/pre_tool.py`, hook configuration, and focused hook/status tests.
5. Expand T13's scope to include pre-tool protection and its tests.
6. Assign the already-present requirement-ID parser change in `scripts/osr.py` to an explicit card. If owned by T0, expand T0 and add a behavioral test for R4b/R5a parsing; do not silently claim the edit belonged to the old card.
7. Add requirements for strict command authorization (T17), review-pack scope (T18), integration/benchmark validation (T19), documentation/release preparation (T20), and installed parity (T21).
8. Put required authoritative files and relevant implementation functions in each card's context. T10-T16 currently provide too little implementation context for a fresh builder.
9. Use a confirmed full-discovery command for formal card verification where practical. Narrow test commands remain development checks. This avoids continually changing approved configuration as new modules are added.
10. Define a reviewer strategy and a policy for approval migration in test fixtures before T13.
11. Make the hook contract's source of truth the captured vendor document: Stop uses `decision: "continue"`; do not copy the changelog's `"block"` claim.
12. Explicitly distinguish breaking security corrections from optional new fields. Strict confirmation and approval changes cannot honestly promise identical legacy behavior.

### Decisions to put in the approval packet

- **T0 dependency:** approve moving normalized counts to T15 as above.
- **Legacy evidence:** keep old ledger bytes intact. Proposed policy: legacy evidence used to justify a current requirement produces `UNCLASSIFIED-LEGACY` and audit exit 2; unrelated historical entries remain disclosed but do not permanently prevent a new fully evidenced workflow from passing. This refines the current plan's broad wording and needs approval.
- **Unprotected projects:** preserve an explicitly documented unprotected compatibility mode with prominent audit warnings; protected projects require the new secret mechanism. Decide whether release policy permits an unprotected audit to exit 0 or requires exit 2. Tests must encode the chosen policy, not leave it implicit.
- **Formal confirmation:** recommend exact confirmed command strings initially. Explicit approved variants can be separate entries. Do not authorize an entire interpreter or shell.
- **Test-first reviews:** the existing roadmap calls for human approval of failing tests before implementation. Batch focused red-test review per packet where applicable; do not infer that this planning document removes that requirement.

Run `plan-check` and `task-check --all`. These prove structure only. Present the diff and decisions. The real operator must run `approve-plan`; the agent must not do so. Existing instructions reserve supervisory commands to the human. No approval is needed merely to prepare this reviewable plan.

## 4. Execution order

```text
Planning reconciliation
  -> T0 baseline closure
  -> T10 current evidence and audit freshness
  -> T17 command authorization
  -> T11 structured status and hook behavior
  -> T12 terminal assessment
  -> T13 approval protection
  -> T14 quick/config integrity
  -> T15 runner and attempt-specific test evidence
  -> T16 test-integrity heuristics
  -> T18 review-pack boundaries
  -> T19 integration and adversarial benchmark
  -> T20 docs/version/release preparation
  -> T21 installed-copy parity
```

Use serial dependencies: most packets edit the same CLI. Do not parallelize those edits. If a packet needs splitting, create a new card before changing scope; each formal card still has its own tests, reviews and closure.

## 5. Packet definitions

### T0 — Close the baseline repair without rebuilding completed work

Read: current T0, deviations, version-consistency tests, sync implementation and tests, requirement parser if assigned here.

Files: current T0 allowed files, plus the explicitly approved parser scope if applicable. Installation itself moves to T21 so later changes do not immediately stale the copy.

Work:

- Retain dynamic version consistency and V1-V12 assertions.
- Preserve the approved sync file set and explicit target requirement.
- Preserve opt-in pruning; default sync must not delete extras.
- Align acceptance-test names and establish actual captured full-suite evidence.
- Identify and preserve unrelated pre-existing changes.

Acceptance:

- Existing 78 tests remain passing unless new meaningful tests increase the count.
- Version equality holds across runtime, package metadata, default benchmark report and top changelog.
- Missing/different/extra files inside the sync set are detected; extras outside it follow the existing approved policy.
- Any parser change has positive and malformed/duplicate-ID coverage.
- No fabricated red run for already-fixed tests. Cite historical evidence honestly or demonstrate the old behavior in an isolated baseline copy.

Focused checks: `python -m unittest tests.test_sync_skill -v`, relevant existing version/parser tests. Finish with formal OSR verification and reviews.

### T10 — Bind completion to current inputs and classify evidence

Read functions: `Ledger.append`, `verify_chain`, `input_hash`, `cmd_start`, `cmd_verify`, `cmd_review`, `cmd_done`, `requirement_rows`, `cmd_audit`, `gate_status`.

Files: `scripts/osr.py`, new `tests/test_evidence_classes.py`, necessary existing test fixtures, V14 evaluator in `evals/eval_suite.py`.

Work:

- Define an explicit registry for event types and their evidence role. Distinguish administrative events from evidence-bearing events; no accidental default evidence class.
- Classify direct execution outcomes as observed, static/output-derived approximations as heuristic, and human declarations as attested.
- A verify event can contain observed execution results and heuristic parser/check results. Do not label every nested result observed merely because the command executed.
- Record the task/card/context identity and approved plan/config identity needed to validate completion.
- Require done evidence newer than the relevant current approval and matching current card/context inputs; validate current code and review freshness too.
- Reject task-ID reuse, changed cards, stale reviews and stale conformance evidence as proof of current completion.
- Keep legacy hash chains verifiable without rewriting entries. Apply the approved legacy-evidence policy in audit.
- Retain `HUMAN-SIGNED` for manual requirements; observed evidence alone must not bypass manual signoff or other completion gates.

Acceptance tests:

- Fresh complete control passes.
- Reused done ID with a different card is STALE.
- Changed context, code, plan or configuration cannot inherit VERIFIED.
- A new approval does not silently validate old done entries.
- Heuristic-only/attested-only evidence does not become automatic VERIFIED.
- Current legacy evidence is disclosed with the approved non-green outcome.
- Legacy chain verification succeeds without rehashing historical entries.
- Unknown evidence event types fail explicitly.

V14 includes literal, disguised, subtle and task-ID-reuse variants, each with a clean control.

### T17 — Authorize the command, not just its interpreter

Read functions: `is_verify_cmd_confirmed`, `confirmed`, `validate_card`, `cmd_confirm`, `cmd_fixture_capture`, and all callers of the confirmation helper.

Files: `scripts/osr.py`, new `tests/test_command_authorization.py`, existing fixtures that rely on permissive command matching, benchmark controls that need explicit confirmation.

Work:

- Reject empty confirmation registries unless the explicitly approved no-command mode applies; no-command mode must not silently authorize arbitrary execution.
- Use exact confirmed command identity as the initial policy. Avoid broad shell normalization that could change meaning.
- Check ledger-backed successful confirmation, not only a mutable `verified` boolean.
- Reject interpreter substitution, changed module/payload, added shell operators and unapproved argument variants.
- Apply the same authorization semantics to task verification, conformance, fixture capture and the later quick implementation.
- Adjust isolated test setup to confirm the actual command before approving its configuration. Do not weaken the authorization gate to keep fixtures convenient.

Acceptance: a confirmed unittest command does not authorize `python -c`, another module, a different executable, an appended shell command or an unconfirmed selection. An exact confirmed command passes. Changed command configuration invalidates its previous evidence.

### T11 — Structured status and bounded contract-correct hooks

Files: `scripts/osr.py`, `integrations/antigravity/stop_hook.py`, `pre_tool.py`, `hooks.json`, `tests/test_stop_hook.py`, new focused status/pre-tool tests, V15 evaluator.

Read the captured vendor contract. Do not infer a schema from the current implementation or test expectations.

Work:

- Make `status --json` emit one JSON object, no Markdown or incidental stdout.
- Include machine-readable completion, approval validity, pending-human action, task states, next action and loop-guard information. Keep human-readable status available.
- Keep a status query observational; do not append ledger events merely because status is read.
- Make Stop consume structured status. Emit only fields appropriate to the documented Stop contract.
- Allow stopping when human action is required. Never force an approval loop.
- Persist an atomic loop guard keyed to meaningful workflow state, allowing stop after three consecutive identical blocks; genuine progress resets it.
- Record guard-release events through an OSR-supported operation, not by editing ledger JSON in the hook.
- Define malformed input/status failure behavior explicitly and visibly; no silent successful-completion claim.
- Validate PreToolUse schema, protected paths, traversal, alternate tool arguments and scoped edits against the supported harness contract. State that shell-command regexes do not establish OS-level isolation.

Acceptance: documented contract fixtures, three identical blocks, progress reset, human-pending stop, no workflow, malformed state, concurrent counter writes, and protected-path cases. Include archived task states in a test so stale historical tasks do not cause endless continuation.

V15 must distinguish protocol correctness from loop-guard behavior. Contract tests use parseable, source-linked fixtures; vendor examples containing comments/ellipsis must not be blindly passed to `json.loads`.

### T12 — Assess the actual agent terminal without granting real authority

Files: `scripts/test_agent_tty.py`, `.ai/TTY_ANALYSIS.md`, focused probe tests if added to the card.

Work:

- Extend the diagnostic to exercise a harmless interactive challenge/getpass path with timeout/EOF behavior. Never request, print or store a real approval secret.
- Run it in the real Antigravity agent terminal and a human-operated terminal. A Codex terminal run is not evidence about Antigravity.
- Record harness identity, command, TTY state, whether input can be supplied, exit behavior and limitations.
- If an approval-command rehearsal is required, the human supervises an isolated disposable workflow with a dummy secret; do not execute supervisory commands against the live repository as the agent.
- Apply the decision rule: if the agent can answer prompts, document that prompting does not separate human authority; require external access controls for that guarantee.
- Prepare a follow-up issue draft if needed; publishing it is a separate action.

Acceptance: empirical report and real human signoff. If the harness is unavailable, report BLOCKED/UNVERIFIED honestly and complete independent preparation only. Do not simulate the missing observation.

### T13 — Protected approvals, migration and testable boundaries

Files: `scripts/osr.py`, `integrations/antigravity/pre_tool.py`, new `tests/test_approval_scrypt.py`, affected existing setup fixtures, V17 evaluator, narrowly scoped approval documentation if necessary.

Work:

- Implement salted `hashlib.scrypt` verification with explicit stored parameters and constant-time comparison.
- Implement `set-secret`, confirmation, old-secret verification for rotation, and fingerprint linkage to ledger evidence.
- Remove plaintext `--secret`/environment input from protected approval paths; never log the entered secret.
- Fail protected operations closed without a controlling terminal; handle EOF and interrupt safely.
- Refuse legacy unsalted configuration for protected operations until the human migrates it.
- Cover approve-plan, unblock, reset, signoff and sensitive waivers consistently.
- Record unprotected approvals under the policy approved in planning reconciliation.
- Bind sensitive waivers to task/attempt/check or approved configuration identity so they do not become permanent blanket exemptions.
- Update hook protections for supported secret-access surfaces while documenting their limits.

Testing boundary: inject/mock input only inside unit tests or use an isolated PTY fixture with dummy secrets. Do not add a production environment variable or debug flag that bypasses authentication for tests. Preserve meaningful CLI integration coverage.

Acceptance: correct/wrong secret, unique salts, rotation, fingerprint mismatch, no TTY, EOF, interrupt, legacy migration, post-approval setup warning, sensitive flags and no secret leakage in logs/errors. V17 adds evasions plus clean controls.

### T14 — Quick mode and test-configuration integrity

Files: `scripts/osr.py`, new `tests/test_quick_hardening.py`, V16 evaluator, relevant existing quick tests.

Work:

- Make quick verify the chain and authorize its command using T17.
- Reject quick during an active formal task.
- Share the applicable static-check and execution pipeline; do not duplicate a weaker quick implementation.
- Define a reliable quick baseline: tracked modifications, staged/unstaged changes, untracked files, deletions and renames. Define non-Git behavior explicitly; fail or mark unsupported evidence UNVERIFIED rather than assuming a nonexistent baseline.
- Fingerprint the approved test-config set at confirmation: pytest.ini, setup.cfg, tox.ini, pyproject.toml, Jest/Vitest configurations, package.json scripts, ESLint configs and tsconfig.json.
- Detect creation, deletion and modification relative to that fingerprint in verify and quick. For package.json compare the declared scripts subset deterministically.
- A config bypass requires protected human authorization and records its exact scope. Decide whether it grants one use or updates an approved fingerprint; it must not silently authorize future drift.
- Report every intentionally skipped formal gate in stdout and ledger. Quick does not finish a task or satisfy spec/quality review.

Acceptance: valid control, corrupted chain, unconfirmed/weak command, active task, config add/delete/change, allowed config decision, scope violations, Git path edge cases, and explicit skipped-gate reporting. V16 exercises both chain and authorization failures.

### T15 — Runner counts and evidence from this exact attempt

Files: `scripts/osr.py`, new `tests/test_runner_parsers.py`, captured `docs/vendor/runner_outputs/*`, V18 evaluator, affected runner fixtures.

Work:

- Record base commit when available and snapshot copies/hashes needed for dirty and non-Git starting trees. New/changed tests must be measured against the task-start state, not just HEAD when the start was already dirty.
- Capture real unittest/pytest output with provenance and include passing, failing, zero-test, skipped-only and non-verbose cases. Keep pytest a test-environment dependency, not a runtime dependency of osr.py.
- Record parsed executed/pass/fail/skip counts as heuristic evidence alongside the observed exit outcome; store the count in confirmation records and expose it in status.
- Require positive executed-test evidence for test verification. Do not demand test counts from legitimate compiler/linter/conformance commands: declare and enforce command roles.
- Detect newly added/modified test identities and require execution evidence for them. Preserve fully qualified names; remove substring matches that confuse similarly named tests.
- Scope XML/JSON result artifacts to the current command and attempt with captured identity/hash. Never scan unrelated old `.ai/logs/*.xml` as current evidence.
- Use `LC_ALL=C` and `PYTHONIOENCODING=utf-8` where applicable. Unknown/localized output gets an actionable UNVERIFIED outcome, not invented counts.
- Treat non-verbose test runs consistently: require an approved verbose equivalent or mark identity coverage UNVERIFIED.
- Keep Jest/Vitest experimental until their evidence has real contract fixtures; do not fabricate support.
- Repair command-level baseline keys (`task_0` versus `task`) if retained for red/green summaries. Do not describe command-level transitions as proof that each negative test failed first.

Acceptance: positive/zero/skipped-only counts; unparseable output; changed tests omitted; name collision; stale XML with empty current output; altered artifact hash; non-Git fallback; dirty starting tree; compiler command without test counts; and correctly scoped current artifacts. V18 includes stale-output evasion.

### T16 — Test-integrity checks and negative-test obligations

Files: `scripts/osr.py`, new `tests/test_assertionless_scan.py`, relevant existing hardening tests, V19 evaluator, task-card template/reference sections if added to scope.

Work:

- Add Python AST and JS/TS heuristic checks for assertionless new/modified tests and extended tautologies.
- Handle legitimate assertion mechanisms such as assertRaises/pytest.raises and helper assertions conservatively. Unknown helper semantics are heuristic uncertainty, not proof of vacuity.
- Detect unapproved selection flags and path filters; distinguish selection from options such as unittest's unrelated `-t` top-level-directory flag. Use runner-specific argument rules.
- Wire the same checks into formal verify and quick.
- Enforce the approved per-seam negative-test obligation, including an absent field. Define an explicit seam-to-test mapping if the flat list cannot establish coverage; document compatibility handling rather than silently guessing associations.
- Require exact current-attempt execution of named negative tests using T15. Missing mandatory negative tests must not yield a passing verify followed only by a surprise at done.
- Update tests that intentionally asserted a bypass succeeds into regression tests that assert it is rejected; preserve the attack scenario and clean control. This is a behavior correction, not permission to remove coverage.

Acceptance: literal/disguised/subtle vacuity, valid helper/exception cases, selection exemptions with genuine authorization, similarly named tests, omitted negative_tests, and equivalent enforcement in verify/quick. V19 remains explicitly heuristic, not a mutation-testing guarantee.

### T18 — Review only the task's actual changes

Files: `scripts/osr.py`, new `tests/test_review_pack_scope.py`, existing review-pack tests.

Work:

- Build the primary review diff from the task-start baseline and allowed files.
- Include staged, unstaged, added, deleted, renamed and applicable non-Git changes accurately.
- List out-of-scope changed paths separately without presenting their contents as task implementation.
- Preserve acceptance criteria, card, declared seams, authoritative source excerpts and adversarial directive.
- Exclude unrelated governance diffs, previous review reasoning and builder notes. If any input is user-authored text, treat it as review data rather than privileged instructions.

Acceptance: two tasks' unrelated changes are separated; pre-existing dirty content is not mislabeled as new task work; required untracked/staged changes appear; upstream citations remain inspectable; deleted files are represented; unrelated notes do not leak into the primary diff.

### T19 — Integrate and prove the new gates against real baselines

Files: `evals/eval_suite.py`, necessary benchmark helpers, new integration tests, existing regression fixtures, CI validation changes if approved in this card.

Work:

- Finish V14-V19, preserving V1-V12. V13 remains reserved unless deliberately assigned.
- Each new vector has a passing clean control and explicit expected gate ID. Unexpected exceptions, missing dependencies and invalid setup are ERROR, not CAUGHT.
- Add a genuine baseline runner that targets a pinned v0.3.1 commit in an isolated checkout/copy. Do not use the `version="0.3.0"` relabel path as historical evidence.
- Keep source revision, runtime version, platform, command and result in reports. Current uncommitted tree identity must be distinguishable from its HEAD commit.
- Run equivalent attack/control scenarios against baseline and current code. Unsupported baseline commands are setup differences, not automatically successful defenses or attacks.
- Test the full lifecycle and changed-plan/task reuse, manual pending, protected approvals, hook human-pending exits, quick integrity and stale artifacts.
- Reconcile old tests with new exact confirmation and approval contracts using real isolated setup, never production bypass switches.
- Verify installed integration behavior in a disposable workspace. The existence of hook source files does not demonstrate installation.

Acceptance: full suite green; controls pass; intended baseline weaknesses reproduced; new gates catch their attacks; known misses and errors reported separately; no unsupported cross-platform claims. Run remote CI only when available/authorized, and retain the actual run evidence.

### T20 — Documentation, metadata and release candidate

Files: `SKILL.md`, `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `evals/README.md`, `integrations/README.md`, relevant `references/*`, `assets/task-card.md`, `pyproject.toml`, CLI version, default benchmark version and `.github/workflows/test.yml` as explicitly listed in the card.

Work:

- Bump version to 0.3.2 only after behavior is implemented and integration checks pass.
- Correct quick-mode descriptions, approval setup, hook schema, test-count claims and obsolete V11/V12 backlog text.
- Replace absolute promises such as "no silent failure" with scoped claims tied to supported checks and trust boundaries.
- Document observed/heuristic/attested evidence, legacy handling, exact command confirmation, unsupported runners and migration behavior.
- State that test-output parsing does not establish semantic test quality or resist arbitrary forged runner output.
- Update optional seam/fixture/kind/negative-test template guidance.
- Resolve pre-commit documentation: current plan-check proves plan structure, not unchanged human approval. Either accurately document this limitation or implement approval enforcement under a separately scoped/tested requirement.
- Describe the actual CI matrix separately from verified run results. No invented CI URL or release evidence.
- Prepare release notes and a reproducible checklist. No push, tag, merge or publication is implied by this handoff.

Acceptance: all version sources agree; docs match tested behavior; links and documented commands resolve; full verification passes after edits; unsupported guarantees are removed.

### T21 — Synchronize the installed skill after the final source changes

Files: explicit installation target supplied by the operator, and any approved sync-test fixes. Preserve the prior approved SYNC_FILES/SYNC_DIRS policy.

Work:

- First run `sync_skill.py --check --target <explicit-target>`.
- Sync only to the explicitly authorized target; do not infer permission for another account or install location.
- Do not prune by default. Inspect and obtain the necessary scope authorization before deleting extras.
- Re-run the same hash check after sync and record the result.
- Smoke-test the installed CLI from a disposable project, not the live development workflow.
- Decide/document which tests are repository-only: the sync set excludes pyproject.toml and docs/vendor, while some tests depend on them. Do not falsely advertise the installed directory as a complete source checkout; do not broaden the sync set without revisiting the recorded decision.

Acceptance: the declared shipped set matches hashes; installed CLI reports 0.3.2; disposable smoke test passes; intentionally excluded assets and any retained extras are disclosed. Do not claim the whole destination is identical when only a declared subset is checked.

## 6. Review and completion rules for every packet

1. Write focused adversarial regression tests and a clean control before implementing a new gate. Obtain the existing required test approval where applicable.
2. Implement only the card. Avoid opportunistic refactors of the 2,000+ line CLI; extract small shared helpers only when the packet needs them.
3. Run focused tests, then the approved formal verify command. Preserve full failure logs; a nonzero result cannot be called passing.
4. Generate a review pack. Until T18 is complete, reviewers independently identify task files because the pack's diff may be broader than the card.
5. In a fresh reviewer session, inspect actual files, changed tests and authoritative sources. Cite specific deficiencies rather than relying on the builder's summary.
6. Record spec and quality reviews through OSR. Resolve findings, then reverify/review changed code.
7. Run `done` only when the actual gates permit it. If gates are defective, fix them through an approved scoped task rather than editing state.
8. Hand off the short state record and the next required action.

Real human operations: plan approval, required failing-test approval, T12 signoff, protected secret initialization/migration/rotation, sensitive waivers, and any required unblock/reset. The agent prepares concrete diffs and instructions before requesting action. It must not sign as the human. These boundaries come from `SKILL.md` Iron Rule 10 and `.agents/rules/osr-iron-rules.md`; test-first approval is stated in `ROADMAP.md`.

## 7. Copy/paste prompts

### First session: prepare the revised plan

```text
Use GPT-6.1-sol for this repository task.

Read docs/GPT-6.1-SOL-IMPLEMENTATION-PLAN.md sections 1-4,
SKILL.md, applicable repository rules, .ai/PLAN.md and
.ai/T0-DEVIATIONS.md. Inspect current status and git diff before editing.

Perform only planning reconciliation. Preserve existing work and task IDs.
Prepare corrected PLAN.md and bounded task cards, including the missing
scopes/dependencies and new T17-T21 work. Use actual source/test names.
Do not implement features, modify the ledger/state, approve the plan,
run real supervisory commands, sync an installation or publish anything.

Run plan-check and task-check --all. Explain the small set of decisions
requiring human approval and present the concrete planning diff.
Keep the final handoff under 250 words, with links to the revised artifacts.
```

### Builder session: replace TASK_ID with the approved current task

```text
Implement only TASK_ID using GPT-6.1-sol.

Read applicable rules, SKILL.md, osr next, the approved task card,
its mapped requirements, its packet in
docs/GPT-6.1-SOL-IMPLEMENTATION-PLAN.md, and the listed context files.
Inspect existing changes first. Preserve unrelated work.

Write meaningful focused regression tests and clean controls for the gate.
Follow required test approval, then implement within allowed_files.
Keep scripts/osr.py stdlib-only and Python 3.8-compatible.
Do not weaken tests, invent evidence, bypass governance, or run human-only
operations on the live workflow. Ask only for missing decisions or actual
human gates; otherwise continue within the approved card.

Use focused checks while iterating and the required formal verification
before review. Capture full logs; report concise command/exit/count data.
Prepare the review packet and a <=250-word handoff. Do not self-certify
an independent review or start the next task.
```

### Fresh reviewer session

```text
Review TASK_ID in a fresh session. Do not implement unrelated changes.
Read its card, current diff, tests, authoritative sources and captured
verification evidence; do not trust the builder's narrative.

Check every acceptance criterion, fail-closed paths, legacy behavior,
evidence freshness, attack/control pairs and misleading green states.
Confirm no test assertions were weakened merely to pass the suite.
Check that commands and gate IDs actually exist.

Write the required spec/quality reviews with real file/line citations.
If something fails, give actionable findings; do not waive it or mark done.
If builder and reviewer use the same model, report that accurately.
Keep the user-facing result concise and distinguish verified from unverified.
```

### Resume after interruption

```text
Resume TASK_ID. Read osr next, the card, current git diff and the last short
handoff. Reconcile them with actual files and logs; do not reconstruct old
tool output. Continue the next authorized action. Do not restart completed
work or reread unrelated historical reports.
```

## 8. Release-readiness checklist

- [ ] Corrected plan approved; current task IDs bound to current evidence.
- [ ] T0 and T10-T21 complete or explicitly unresolved with honest status.
- [ ] Full suite passes with actual count/output captured.
- [ ] V1-V12 preserved; V14-V19 have controls and genuine baseline evidence.
- [ ] No stale XML, stale task identity or interpreter-only confirmation accepted.
- [ ] Quick reports its skipped gates and enforces its promised protections.
- [ ] Hook contract/loop behavior tested; real harness observations recorded.
- [ ] Manual signoff and approval boundary limitations disclosed.
- [ ] Audit classifies evidence and handles legacy records as approved.
- [ ] Version/docs agree; CI claims have actual evidence.
- [ ] Installed declared file set matches source and installed smoke check passes.
- [ ] External anchor is held outside the agent's writable trust boundary.
- [ ] Audit exit 0 is supported by actual evidence; exit 2 remains pending, not complete.
- [ ] Any publication/tag/push is separately authorized and verified after execution.
