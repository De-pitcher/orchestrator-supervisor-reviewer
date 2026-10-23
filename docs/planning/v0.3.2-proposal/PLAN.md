# Proposed plan: OSR v0.3.2 hardening

## Goal
Deliver current-input/attempt-bound evidence, bounded vendor-correct hooks, defensible approvals and honest heuristic/manual reporting. Prepared 2026-10-23 for human review only; active plan/cards/state remain unchanged. Decisions D1-D5 await approval.

## Non-goals
- Rebuilding completed work, reusing archived IDs, manually rewriting ledger/state or implementing features in this session.
- Inferring external isolation from prompts or shell regexes, semantic test quality from parsed output or historical evidence from relabeled reports.
- Publishing, merging, tagging, pushing or syncing to an inferred installation target.
- Weakening tests except the already human-approved, narrowly documented .ai/T0-DEVIATIONS.md D1-D4 exceptions, which remain binding.

## Task order
T0 -> T10 -> T17 -> T11 -> T12 -> T13 -> T14 -> T15 -> T16 -> T18 -> T19 -> T20 -> T21.
Preserve T0 and T10-T16. T17-T21 have no current/archived cards or ledger ID ownership at preparation. Serial dependencies avoid competing CLI edits. This proposal changes no task state.

## Requirements
- R0: Close the baseline repair without rebuilding completed work (T0)
  - AC: Retain actual OsrTests.test_phase6_version_and_docs_integrity, test_phase6_benchmark_and_honest_reporting and test_adversarial_eval_suite_benchmarks_catch_rate; dynamic runtime/package/default benchmark/top changelog version equality and V1-V12 CAUGHT assertions remain under deviations D1.
  - AC: Capture confirmed full-discovery/global verification output and observed exit. Historical count was 78 passing tests; meaningful new tests may increase it. Normalized parsed positive-count storage/status moves to R5a/T15, subject to D1 approval.
  - AC: Keep explicit-target sync hash checks and opt-in pruning. Existing tests in tests/test_sync_skill.py: test_sync_skill_real_repo_sync_and_check_smoke, test_sync_skill_file_set_included_and_excluded, test_sync_skill_negative_missing_file, test_sync_skill_negative_differing_file, test_sync_skill_negative_extra_file_inside_synced_item, test_sync_skill_extra_outside_synced_items_not_flagged and test_sync_skill_sync_without_prune_keeps_extras. Preserve deviations D2-D4. Actual installation belongs to T21.
  - AC: Explicitly own existing scripts/osr.py parse_plan regex change and add meaningful R4b/R5a positive, malformed and duplicate-ID behavioral coverage in tests/test_requirement_ids.py. Cite historical evidence honestly or reproduce old behavior in an isolated baseline; fabricate no red run.
  - Check: auto

- R1: Bind completion to current inputs and classify evidence (T10)
  - AC: Define an explicit registry for event types and their evidence role. Distinguish administrative events from evidence-bearing events; no accidental default evidence class.
  - AC: Classify direct execution outcomes as observed, static/output-derived approximations as heuristic, and human declarations as attested.
  - AC: A verify event can contain observed execution results and heuristic parser/check results. Do not label every nested result observed merely because the command executed.
  - AC: Record the task/card/context identity and approved plan/config identity needed to validate completion.
  - AC: Require done evidence newer than the relevant current approval and matching current card/context inputs; validate current code and review freshness too.
  - AC: Reject task-ID reuse, changed cards, stale reviews and stale conformance evidence as proof of current completion.
  - AC: Keep legacy hash chains verifiable without rewriting entries. Apply the approved legacy-evidence policy in audit.
  - AC: Retain `HUMAN-SIGNED` for manual requirements; observed evidence alone must not bypass manual signoff or other completion gates.
  - AC: Fresh complete control passes.
  - AC: Reused done ID with a different card is STALE.
  - AC: Changed context, code, plan or configuration cannot inherit VERIFIED.
  - AC: A new approval does not silently validate old done entries.
  - AC: Heuristic-only/attested-only evidence does not become automatic VERIFIED.
  - AC: Current legacy evidence is disclosed with the approved non-green outcome.
  - AC: Legacy chain verification succeeds without rehashing historical entries.
  - AC: Unknown evidence event types fail explicitly.
  - Check: auto

- R6: Authorize the command, not just its interpreter (T17)
  - AC: Reject empty confirmation registries unless the explicitly approved no-command mode applies; no-command mode must not silently authorize arbitrary execution.
  - AC: Use exact confirmed command identity as the initial policy. Avoid broad shell normalization that could change meaning.
  - AC: Check ledger-backed successful confirmation, not only a mutable `verified` boolean.
  - AC: Reject interpreter substitution, changed module/payload, added shell operators and unapproved argument variants.
  - AC: Apply the same authorization semantics to task verification, conformance, fixture capture and the later quick implementation.
  - AC: Adjust isolated test setup to confirm the actual command before approving its configuration. Do not weaken the authorization gate to keep fixtures convenient.
  - AC: a confirmed unittest command does not authorize `python -c`, another module, a different executable, an appended shell command or an unconfirmed selection. An exact confirmed command passes. Changed command configuration invalidates its previous evidence.
  - Check: auto

- R2: Structured status and bounded contract-correct hooks (T11)
  - AC: Make `status --json` emit one JSON object, no Markdown or incidental stdout.
  - AC: Include machine-readable completion, approval validity, pending-human action, task states, next action and loop-guard information. Keep human-readable status available.
  - AC: Keep a status query observational; do not append ledger events merely because status is read.
  - AC: Make Stop consume structured status. Emit only fields appropriate to the documented Stop contract.
  - AC: Allow stopping when human action is required. Never force an approval loop.
  - AC: Persist an atomic loop guard keyed to meaningful workflow state, allowing stop after three consecutive identical blocks; genuine progress resets it.
  - AC: Record guard-release events through an OSR-supported operation, not by editing ledger JSON in the hook.
  - AC: Define malformed input/status failure behavior explicitly and visibly; no silent successful-completion claim.
  - AC: Validate PreToolUse schema, protected paths, traversal, alternate tool arguments and scoped edits against the supported harness contract. State that shell-command regexes do not establish OS-level isolation.
  - AC: documented contract fixtures, three identical blocks, progress reset, human-pending stop, no workflow, malformed state, concurrent counter writes, and protected-path cases. Include archived task states in a test so stale historical tasks do not cause endless continuation.
  - Check: auto

- R4b: Assess the actual agent terminal without granting real authority (T12)
  - AC: Extend the diagnostic to exercise a harmless interactive challenge/getpass path with timeout/EOF behavior. Never request, print or store a real approval secret.
  - AC: Run it in the real Antigravity agent terminal and a human-operated terminal. A Codex terminal run is not evidence about Antigravity.
  - AC: Record harness identity, command, TTY state, whether input can be supplied, exit behavior and limitations.
  - AC: If an approval-command rehearsal is required, the human supervises an isolated disposable workflow with a dummy secret; do not execute supervisory commands against the live repository as the agent.
  - AC: Apply the decision rule: if the agent can answer prompts, document that prompting does not separate human authority; require external access controls for that guarantee.
  - AC: Prepare a follow-up issue draft if needed; publishing it is a separate action.
  - AC: empirical report and real human signoff. If the harness is unavailable, report BLOCKED/UNVERIFIED honestly and complete independent preparation only. Do not simulate the missing observation.
  - Check: manual
  - Script: scripts/test_agent_tty.py

- R4: Protected approvals, migration and testable boundaries (T13)
  - AC: Implement salted `hashlib.scrypt` verification with explicit stored parameters and constant-time comparison.
  - AC: Implement `set-secret`, confirmation, old-secret verification for rotation, and fingerprint linkage to ledger evidence.
  - AC: Remove plaintext `--secret`/environment input from protected approval paths; never log the entered secret.
  - AC: Fail protected operations closed without a controlling terminal; handle EOF and interrupt safely.
  - AC: Refuse legacy unsalted configuration for protected operations until the human migrates it.
  - AC: Cover approve-plan, unblock, reset, signoff and sensitive waivers consistently.
  - AC: Record unprotected approvals under the policy approved in planning reconciliation.
  - AC: Bind sensitive waivers to task/attempt/check or approved configuration identity so they do not become permanent blanket exemptions.
  - AC: Update hook protections for supported secret-access surfaces while documenting their limits.
  - AC: correct/wrong secret, unique salts, rotation, fingerprint mismatch, no TTY, EOF, interrupt, legacy migration, post-approval setup warning, sensitive flags and no secret leakage in logs/errors. V17 adds evasions plus clean controls.
  - AC: inject/mock input only inside unit tests or use an isolated PTY fixture with dummy secrets. Do not add a production environment variable or debug flag that bypasses authentication for tests. Preserve meaningful CLI integration coverage.
  - Check: auto

- R3: Quick mode and test-configuration integrity (T14)
  - AC: Make quick verify the chain and authorize its command using T17.
  - AC: Reject quick during an active formal task.
  - AC: Share the applicable static-check and execution pipeline; do not duplicate a weaker quick implementation.
  - AC: Define a reliable quick baseline: tracked modifications, staged/unstaged changes, untracked files, deletions and renames. Define non-Git behavior explicitly; fail or mark unsupported evidence UNVERIFIED rather than assuming a nonexistent baseline.
  - AC: Fingerprint the approved test-config set at confirmation: pytest.ini, setup.cfg, tox.ini, pyproject.toml, Jest/Vitest configurations, package.json scripts, ESLint configs and tsconfig.json.
  - AC: Detect creation, deletion and modification relative to that fingerprint in verify and quick. For package.json compare the declared scripts subset deterministically.
  - AC: A config bypass requires protected human authorization and records its exact scope. Decide whether it grants one use or updates an approved fingerprint; it must not silently authorize future drift.
  - AC: Report every intentionally skipped formal gate in stdout and ledger. Quick does not finish a task or satisfy spec/quality review.
  - AC: valid control, corrupted chain, unconfirmed/weak command, active task, config add/delete/change, allowed config decision, scope violations, Git path edge cases, and explicit skipped-gate reporting. V16 exercises both chain and authorization failures.
  - Check: auto

- R5a: Runner counts and evidence from this exact attempt (T15)
  - AC: Record base commit when available and snapshot copies/hashes needed for dirty and non-Git starting trees. New/changed tests must be measured against the task-start state, not just HEAD when the start was already dirty.
  - AC: Capture real unittest/pytest output with provenance and include passing, failing, zero-test, skipped-only and non-verbose cases. Keep pytest a test-environment dependency, not a runtime dependency of osr.py.
  - AC: Record parsed executed/pass/fail/skip counts as heuristic evidence alongside the observed exit outcome; store the count in confirmation records and expose it in status.
  - AC: Require positive executed-test evidence for test verification. Do not demand test counts from legitimate compiler/linter/conformance commands: declare and enforce command roles.
  - AC: Detect newly added/modified test identities and require execution evidence for them. Preserve fully qualified names; remove substring matches that confuse similarly named tests.
  - AC: Scope XML/JSON result artifacts to the current command and attempt with captured identity/hash. Never scan unrelated old `.ai/logs/*.xml` as current evidence.
  - AC: Use `LC_ALL=C` and `PYTHONIOENCODING=utf-8` where applicable. Unknown/localized output gets an actionable UNVERIFIED outcome, not invented counts.
  - AC: Treat non-verbose test runs consistently: require an approved verbose equivalent or mark identity coverage UNVERIFIED.
  - AC: Keep Jest/Vitest experimental until their evidence has real contract fixtures; do not fabricate support.
  - AC: Repair command-level baseline keys (`task_0` versus `task`) if retained for red/green summaries. Do not describe command-level transitions as proof that each negative test failed first.
  - AC: positive/zero/skipped-only counts; unparseable output; changed tests omitted; name collision; stale XML with empty current output; altered artifact hash; non-Git fallback; dirty starting tree; compiler command without test counts; and correctly scoped current artifacts. V18 includes stale-output evasion.
  - Check: auto

- R5b: Test-integrity checks and negative-test obligations (T16)
  - AC: Add Python AST and JS/TS heuristic checks for assertionless new/modified tests and extended tautologies.
  - AC: Handle legitimate assertion mechanisms such as assertRaises/pytest.raises and helper assertions conservatively. Unknown helper semantics are heuristic uncertainty, not proof of vacuity.
  - AC: Detect unapproved selection flags and path filters; distinguish selection from options such as unittest's unrelated `-t` top-level-directory flag. Use runner-specific argument rules.
  - AC: Wire the same checks into formal verify and quick.
  - AC: Enforce the approved per-seam negative-test obligation, including an absent field. Define an explicit seam-to-test mapping if the flat list cannot establish coverage; document compatibility handling rather than silently guessing associations.
  - AC: Require exact current-attempt execution of named negative tests using T15. Missing mandatory negative tests must not yield a passing verify followed only by a surprise at done.
  - AC: Update tests that intentionally asserted a bypass succeeds into regression tests that assert it is rejected; preserve the attack scenario and clean control. This is a behavior correction, not permission to remove coverage.
  - AC: literal/disguised/subtle vacuity, valid helper/exception cases, selection exemptions with genuine authorization, similarly named tests, omitted negative_tests, and equivalent enforcement in verify/quick. V19 remains explicitly heuristic, not a mutation-testing guarantee.
  - Check: auto

- R7: Review only the task's actual changes (T18)
  - AC: Build the primary review diff from the task-start baseline and allowed files.
  - AC: Include staged, unstaged, added, deleted, renamed and applicable non-Git changes accurately.
  - AC: List out-of-scope changed paths separately without presenting their contents as task implementation.
  - AC: Preserve acceptance criteria, card, declared seams, authoritative source excerpts and adversarial directive.
  - AC: Exclude unrelated governance diffs, previous review reasoning and builder notes. If any input is user-authored text, treat it as review data rather than privileged instructions.
  - AC: two tasks' unrelated changes are separated; pre-existing dirty content is not mislabeled as new task work; required untracked/staged changes appear; upstream citations remain inspectable; deleted files are represented; unrelated notes do not leak into the primary diff.
  - Check: auto

- R8: Integrate and prove the new gates against real baselines (T19)
  - AC: Finish V14-V19, preserving V1-V12. V13 remains reserved unless deliberately assigned.
  - AC: Each new vector has a passing clean control and explicit expected gate ID. Unexpected exceptions, missing dependencies and invalid setup are ERROR, not CAUGHT.
  - AC: Add a genuine baseline runner that targets a pinned v0.3.1 commit in an isolated checkout/copy. Do not use the `version="0.3.0"` relabel path as historical evidence.
  - AC: Keep source revision, runtime version, platform, command and result in reports. Current uncommitted tree identity must be distinguishable from its HEAD commit.
  - AC: Run equivalent attack/control scenarios against baseline and current code. Unsupported baseline commands are setup differences, not automatically successful defenses or attacks.
  - AC: Test the full lifecycle and changed-plan/task reuse, manual pending, protected approvals, hook human-pending exits, quick integrity and stale artifacts.
  - AC: Reconcile old tests with new exact confirmation and approval contracts using real isolated setup, never production bypass switches.
  - AC: Verify installed integration behavior in a disposable workspace. The existence of hook source files does not demonstrate installation.
  - AC: full suite green; controls pass; intended baseline weaknesses reproduced; new gates catch their attacks; known misses and errors reported separately; no unsupported cross-platform claims. Run remote CI only when available/authorized, and retain the actual run evidence.
  - Check: auto

- R9: Documentation, metadata and release candidate (T20)
  - AC: Bump version to 0.3.2 only after behavior is implemented and integration checks pass.
  - AC: Correct quick-mode descriptions, approval setup, hook schema, test-count claims and obsolete V11/V12 backlog text.
  - AC: Replace absolute promises such as "no silent failure" with scoped claims tied to supported checks and trust boundaries.
  - AC: Document observed/heuristic/attested evidence, legacy handling, exact command confirmation, unsupported runners and migration behavior.
  - AC: State that test-output parsing does not establish semantic test quality or resist arbitrary forged runner output.
  - AC: Update optional seam/fixture/kind/negative-test template guidance.
  - AC: Resolve pre-commit documentation: current plan-check proves plan structure, not unchanged human approval. Either accurately document this limitation or implement approval enforcement under a separately scoped/tested requirement.
  - AC: Describe the actual CI matrix separately from verified run results. No invented CI URL or release evidence.
  - AC: Prepare release notes and a reproducible checklist. No push, tag, merge or publication is implied by this handoff.
  - AC: all version sources agree; docs match tested behavior; links and documented commands resolve; full verification passes after edits; unsupported guarantees are removed.
  - Check: auto

- R10: Synchronize the installed skill after the final source changes (T21)
  - AC: First run `sync_skill.py --check --target <explicit-target>`.
  - AC: Sync only to the explicitly authorized target; do not infer permission for another account or install location.
  - AC: Do not prune by default. Inspect and obtain the necessary scope authorization before deleting extras.
  - AC: Re-run the same hash check after sync and record the result.
  - AC: Smoke-test the installed CLI from a disposable project, not the live development workflow.
  - AC: Decide/document which tests are repository-only: the sync set excludes pyproject.toml and docs/vendor, while some tests depend on them. Do not falsely advertise the installed directory as a complete source checkout; do not broaden the sync set without revisiting the recorded decision.
  - AC: the declared shipped set matches hashes; installed CLI reports 0.3.2; disposable smoke test passes; intentionally excluded assets and any retained extras are disclosed. Do not claim the whole destination is identical when only a declared subset is checked.
  - Check: auto

## Seams
| seam id | consumer | provider | authoritative source | how it is checked |
|---|---|---|---|---|
| antigravity_hook | integrations/antigravity/stop_hook.py and pre_tool.py | Antigravity Runtime | docs/vendor/antigravity-hooks-2026-10-22.md | T11 source-linked parseable contract cases in full discovery |
| runner_output_unittest | scripts/osr.py | unittest runner | docs/vendor/runner_outputs/unittest_output.txt | T15 provenance-backed real captures and full-discovery conformance |
| runner_output_pytest | scripts/osr.py | pytest runner | docs/vendor/runner_outputs/pytest_output.txt | T15 provenance-backed real captures and full-discovery conformance |

## Interfaces
- Evidence registry distinguishes administrative and evidence-bearing events; observed execution never promotes nested heuristic results. Current identity binds approved plan/config, card/context, code, reviews, command and attempt. Manual requirements retain HUMAN-SIGNED obligations.
- Exact confirmed command strings are the initial authorization identity (D4). Declare command roles: test execution needs positive counts; legitimate compiler/linter/conformance execution does not require test counts. Empty or no-command mode authorizes no arbitrary command. Narrow development variants require separate confirmation before formal use.
- Status --json emits exactly one object for completion, approval validity, pending-human action, current task states, next action and guard state. Status queries append no events. T11 specifies a versioned field schema and explicit error object before implementation. Stop blocks using decision="continue" from captured vendor docs, never changelog "block". Non-continuation permits stopping; malformed state emits a visible diagnostic without claiming completion. Guard-release events use a supported OSR operation, not hook-written ledger bytes.
- Before T13 migrate isolated approval fixtures: inventory tests/test_osr.py Project, evals/eval_suite.py EvalProject and affected test setup helpers. Protected tests use test-only mocked input or isolated PTYs with dummy secrets. Preserve real CLI integration coverage. Unprotected fixtures explicitly declare compatibility mode and assert the approved D3 warnings/exit. Migrate legacy protected fixtures through isolated setup; no production bypass flags/environment inputs. Real initial setup, migration and rotation remain human operations.
- Task-start identity includes dirty/untracked snapshots and base commit when available; review packs and changed-test checks consume it. Result artifacts carry current command/attempt identity and content hash; unrelated old XML is not execution evidence.
- Per-seam negative tests map explicitly in T11/T15; T16 enforces absent obligations and exact current-attempt execution. Any new syntax requires a reviewed card change, not guessed associations.
- Confirmation, approval, evidence freshness and quick security corrections intentionally change permissive v0.3.1 behavior. New optional seam/fixture/kind fields retain compatibility only where safe; there is no blanket identical-legacy-behavior promise.

## Review and verification policy
One builder session per packet; fresh spec/quality reviewer sessions inspect actual files, tests, source contracts and captured outputs. Requested builder is GPT-6.1-sol. A reviewer using the same model is labeled honestly as the same model. Current require_distinct_reviewer=false permits fresh same-model review; if that policy changes, use a real different reviewer or obtain an explicit plan decision. Do not spawn agents just to execute this plan.
ROADMAP.md requires human approval of focused failing tests before implementation. Batch attack/control red-test review per packet (D5); T0 already-fixed tests cite honest historical evidence or real isolated baseline reproduction. No fabricated red run.
Each card uses existing confirmed python -m unittest discover -s tests -v for formal verification, retaining configured global_verify. Conformance also uses discovery to avoid unconfirmed variants. Narrow commands are development checks. Capture complete output/exit/count/log path; reuse unchanged benchmark results within one process. Proposed new test names do not yet exist and are not claims of coverage.
Until T18 reviewers identify task files independently because current review-pack diffs may be broad. Each task still needs actual verification and both reviews; no self-certified independent review. Handoffs remain in transcripts unless their path is explicitly allowed.

## Decisions pending human review
D1: Move normalized positive-count storage/status from R0/T0 to R5a/T15; T0 captures full output and observed exit without an unbuilt parser. Explicitly assign the existing requirement parser edit and new behavioral coverage to T0.
D2: Preserve old ledger bytes. Legacy evidence used for a current requirement is UNCLASSIFIED-LEGACY and audit exit 2; unrelated historical entries remain disclosed without permanently preventing a new fully evidenced workflow from passing. New approval does not validate stale done/review evidence.
D3: Retain documented unprotected compatibility mode with prominent warnings. Recommended release policy: current unprotected approval makes audit exit 2 rather than 0. Protected projects require the new secret mechanism. Tests must encode the actual approved choice.
D4: Require exact confirmed command strings initially, with explicitly approved variants as separate entries. Never authorize an entire interpreter or shell.
D5: Keep test-first human approval; batch focused failing-test review per packet. Fresh same-model review is permitted under current config and honestly labeled; no invented reviewer identity.

## Open questions
OQ1: Actual Antigravity prompt authority remains UNVERIFIED until T12 human signoff. A prompt does not establish separation from an agent able to answer it.
OQ2: T21 installation target is unspecified. Its card must receive an explicit operator target and approved allowed_files update before destination writes; no installation is authorized here.
OQ3: T19 must resolve a real pinned v0.3.1 source revision with provenance; version relabeling is not a historical baseline. Missing harness/dependencies/remote CI remain disclosed limitations.
