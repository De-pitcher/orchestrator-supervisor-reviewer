# osr Improvement Roadmap (for Antigravity + Gemini)

Repo: https://github.com/De-pitcher/orchestrator-supervisor-reviewer

## How to run this roadmap

- **Use the skill to build itself.** Each phase is: plan, task cards, `osr verify`, review. If osr cannot govern its own development, that is useful information.
- **One phase per session.** Give the model only that phase's goal, the files it may touch, and its acceptance test. Never hand it the whole roadmap.
- **Tests before code.** For each phase, the model writes failing tests first (including attempts to cheat the gate). You approve them, then it implements.
- **Independent review.** Have a different model review the diffs, especially for Phases 4 and 5. Security-sensitive work should not be reviewed by the model that wrote it.
- **Order is by dependency.** Hooks and approval tokens need stable JSON output and task state to build on.

## Antigravity capabilities this plan relies on

- Hooks are configured in a `hooks.json` file in the workspace `.agents/` folder or in `~/.gemini/config/`. Only `command` hooks are supported. A hook can hard-block an action with a `deny` decision.
- The permissions engine evaluates Deny first, then Ask, then Allow. It supports deny rules on commands and on file paths (denying read also denies write).
- Terminal sandboxing is in preview on macOS and Linux and listed as coming to Windows. On Windows, lean on deny rules and CI.
- Verify the exact hook event names and payload fields in the current docs before Phase 5. They are not assumed here.

---

## Phase 0: Baseline (about half a day)

- Run the existing tests on your own OS. CI is the only multi-platform coverage and it is not yet green-verified.
- Create a branch.
- Put this roadmap into `.ai/PLAN.md` as requirements R1..Rn, each with an acceptance criterion and `Check: auto|manual`.
- Add `.agents/rules` telling the model to follow the skill's iron rules.

**Done when:** tests are green and you have approved the plan.

## Phase 1: Quick wins and packaging

- Add `--json` output and documented, stable exit codes.
- Add a pyproject entry point so `pipx install` gives you an `osr` command (replaces the alias).
- Add a ledger lock file for concurrent writers.
- Tighten the SKILL.md description so it triggers on explicit orchestration, supervision or plan-driven multi-task work, not on every multi-step change.
- Fix the "five commands" wording in iron rule 10 (it lists four plus a category) and make the README consistent about `waive`.
- If `osr.py` is unwieldy for the model to edit, split it into modules here, using the existing tests as a safety net.

**Done when:** existing tests pass unchanged, plus new tests for JSON output and the lock.

## Phase 2: Red/green evidence

- `start` records a baseline of the test state.
- `verify` can require that new or changed tests fail before the change and pass after.
- The task card's `verify:` command must be one of the confirmed commands.
- Add cheat tests: `verify: true`, a test that cannot fail, and a test weakened by loosening an expectation.

**Done when:** every cheat is rejected and a normal task still passes. Measure false positives on a real small project.

## Phase 3: Requirement to test to run traceability

- Acceptance criteria carry test IDs.
- `verify` parses JUnit or JSON output from the test runner. Start with pytest and Jest.
- `audit` shows that the specific test ran and passed.

**Done when:** a criterion with a missing, skipped or failing test blocks `done`.

## Phase 4: Trust model

- Human-only approvals require a secret the agent does not hold.
- The config file's hash is included in the plan approval, so editing config voids it.
- Add `osr anchor`, which writes the ledger head hash outside `.ai/` (for example a git commit or CI artifact). `ledger-verify` checks against the anchor.

**Caveat:** an agent sharing your shell and filesystem can read an env var or a local key file. Real protection needs the Phase 5 deny rules and CI verification.

**Done when:** adversarial tests (forged approval, rewritten ledger, edited config) all fail verification.

## Phase 5: Antigravity enforcement

- **First step of the session:** have the model read the current Antigravity hooks docs and list the exact event names and payload fields.
- Add `integrations/antigravity/` containing:
  - a `hooks.json` and a pre-action script that reads the active task and denies edits outside `allowed_files`;
  - deny rules for the human-only commands (for example `command(osr approve-plan)`) and a deny on reading the approval secret's path. You run those commands in your own terminal, outside the agent;
  - a completion hook that checks `osr next` before the agent can claim it is done.
- Also add a generic git pre-commit hook and a CI workflow so the project is not tied to one harness.

**Done when:** a scripted agent session attempting scope creep and `approve-plan` is blocked.

## Phase 6: Reviewer bundle and quick path

- `osr review-pack` outputs the diff, the task card and the acceptance criteria only, with no builder explanation, for a fresh session or different model.
- `osr quick --verify "<cmd>"` does a scope diff plus verify only, for small fixes. No cards or review files.

**Done when:** a quick run takes under a minute of ceremony, and the review pack contains nothing from the builder's reasoning.

## Phase 7: Pluggable checkers and evals

- Let `.ai/config.json` declare checkers (a command plus a structured result format) so other languages can plug in without touching `osr.py`.
- Build an adversarial eval suite: seeded cheats (fake pass, weakened test, scope creep, truncation) run against several models, reporting catch rate and false-positive rate.
- Put the numbers in the README and bump the version to v0.2.

**Done when:** the README numbers come from a reproducible run.

---

## Prompt template for each Gemini session

```
Phase N of the roadmap in .ai/PLAN.md.
Goal: [one sentence].
You may touch only: [files].

First write failing tests for each acceptance criterion, including attempts
to cheat the gate, and stop for my approval. Then implement.
Do not change behavior outside this phase.
Run the full test suite and show me the output.
List anything you were unsure about instead of guessing.
```

## Risks

- Phases 4 and 5 are where weaker reasoning does the most damage. Expect a lot of iteration, and do not merge them without an independent review.
- A large single-file `osr.py` is hard for any model to edit safely. Split it early if needed.
