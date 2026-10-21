# orchestrator-supervisor-reviewer

A skill that lets **any AI model** (frontier or not) act as the orchestrator, supervisor and reviewer of a software project, on **any stack**, while a deterministic script, not the AI's own say-so, decides what counts as done.

> **The AI proposes. The tool decides. Nothing the AI says counts as evidence.**

## Why

AI coding agents hallucinate APIs, claim tests passed when they never ran, quietly widen scope, truncate files, weaken tests to get green, review their own work kindly, and loop on the same failed approach. Better prompts reduce this but cannot remove it. This skill makes the cheap-to-check things mechanical:

| AI limitation | What stops it |
|---|---|
| "Tests pass" with no run | `osr verify` runs the commands itself and records the output |
| Hallucinated imports | built-in import and syntax checks (Python, JS/TS), plus your compiler or type-checker as a confirmed command |
| Scope creep | snapshot diff against the task card's `allowed_files` |
| Truncated or elided code | placeholder and shrinkage detection |
| Weakened tests | assertion-count and skip-marker detection; waivers need a human |
| Fake reviews | review files must cite real `file:line "snippet"`, which the tool checks against the code |
| Skipped steps | every command refuses unless the previous gate passed |
| Blind retry loops | failure cap, mandatory triage by layer (spec, plan, prompt, context, environment, model, implementation), retries must change something |
| Stale approvals | work fingerprints; any edit after verify or review invalidates them |
| Lost context | state lives in `.ai/` files, `osr next` re-derives the next step |

It also stays honest about what it cannot check: anything with no machine check is labelled **UNVERIFIED** and routed to a human. See [`references/guarantees.md`](references/guarantees.md).

## What you get

```
SKILL.md                 the instructions the AI reads (short, with reasons)
scripts/osr.py           the enforcement CLI (Python 3.8+, standard library only)
assets/                  templates: PLAN.md, task card, spec review, quality review
references/              triage, task cards, reviewing, weaker models, setups, guarantees
PROMPT-ONLY.md           the same discipline for chat windows with no shell
tests/test_osr.py        end-to-end tests that try to cheat the gates
examples/walkthrough.md  a real run, start to finish
```

## Install

It is a folder. Put it wherever your tool loads skills or project instructions from, or just keep it in your repo.

```
git clone https://github.com/De-pitcher/orchestrator-supervisor-reviewer.git
alias osr='python3 /path/to/orchestrator-supervisor-reviewer/scripts/osr.py'     # macOS / Linux
```

PowerShell: `function osr { python C:\path\to\orchestrator-supervisor-reviewer\scripts\osr.py @args }`

Tools that do not load skill folders: paste the Iron rules and workflow from `SKILL.md` into the tool's rules or system prompt, and keep `scripts/`, `assets/` and `references/` in the repository. Tools with no shell: use `PROMPT-ONLY.md`.

## Quick start

From your project's root:

```
osr init                      # creates .ai/
osr detect                    # guesses build/test/lint commands from marker files
osr confirm-commands          # actually runs them; only working ones count
# fill .ai/PLAN.md (goal, non-goals, requirements with acceptance criteria)
osr plan-check
osr approve-plan --by you     # HUMAN: reviews and approves the plan
# write .ai/tasks/T1.md ...   (self-contained task cards)
osr task-check --all
osr start T1 --model gemini-x
# implement
osr verify T1                 # static checks + real commands, evidence recorded
# write .ai/reviews/T1.spec.md and T1.quality.md
osr review T1 spec --reviewer deepseek-y
osr review T1 quality --reviewer deepseek-y
osr done T1
osr audit                     # requirement -> task -> evidence matrix
```

At any point, `osr next` prints the single next required action. That is the command to give a model that has lost its place.

## Command reference

| Command | Purpose |
|---|---|
| `init`, `detect`, `confirm-commands`, `env-check` | ground truth: which commands really work here |
| `plan-check`, `approve-plan` (human) | validate and lock the plan; editing it voids approval |
| `task-check [--all]` | validate cards: coverage, narrow scope, context budget, real verify command |
| `start`, `check`, `verify`, `review`, `done` | the per-task loop |
| `triage`, `unblock` (human), `reset` (human) | failure handling |
| `waive` (human-approved for sensitive flags), `signoff` (human) | recorded, visible exceptions and manual approvals |
| `next`, `status`, `coverage`, `audit`, `ledger-verify` | orientation and final proof |

## How it works, briefly

- **Snapshot and diff.** `start` records file hashes. Everything after is judged against that, so it works without git.
- **Ledger.** `.ai/ledger.jsonl` is append-only and hash-chained. Evidence is written only by `osr`. Edit it by hand and `ledger-verify` fails.
- **Fingerprints.** Verify and reviews record a fingerprint of the changed files. `done` requires them to match the current code, so edit-after-approval is caught.
- **Triage routing.** The layer you name decides what must change before the next attempt (card or context edited, different model, passing environment check, or the human).

## Guarantees and limits

You get **no silent failure**, not 100% correctness. The plan can be wrong, tests can be weak, and taste has no check. Ways to raise the bar (tests-first approved by a human, a different model as reviewer, type-checkers and mutation testing as confirmed commands) are in [`references/guarantees.md`](references/guarantees.md). The human-only commands and waiver approvals are honor-system unless your harness prevents the AI from running them; see [`references/setups.md`](references/setups.md).

## Status

v0.1. The CLI has 15 end-to-end tests, run on Linux during development. CI is configured for Linux, macOS and Windows with Python 3.9 and 3.12; treat other platforms as untested until CI is green on your fork. Reference checking is built in for Python and JS/TS only. It has not yet been tried across many models and real projects, so real-world reports are the most useful contribution. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT, see [`LICENSE`](LICENSE).
