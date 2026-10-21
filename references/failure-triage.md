# Failure triage

When something fails, the instinct is "fix and rerun". That is right for one kind of failure and wasteful or harmful for the rest. Rerunning the same input on a model that misunderstood it produces more confident wrong code. So: diagnose the layer first, then apply that layer's remedy.

## Contents
- The five questions
- Layers and remedies
- Graph-level failures (tasks pass alone, fail together)
- The retry rule
- Worked examples

## The five questions

Answer with evidence (a file, a line, a command output), not with a feeling. Go in order and stop at the first "no".

1. **Did the builder have every file and fact it needed, and can you point to where each was provided?** No means a **context** fault (missing or bloated context, or invented facts).
2. **Would two competent engineers read the task card the same way?** No means a **prompt** fault (ambiguous, contradictory, key rule buried, no example).
3. **Could the task be finished in one focused session with its own verification?** No means a **plan** fault (task too big, wrong order, interfaces undefined).
4. **Is the requirement itself unambiguous, consistent with the others, and what the human wants?** No means a **spec** fault.
5. **Does the same failure occur when a different model gets the identical card and context?** Yes means the cause is upstream of the model (spec, plan, prompt, context or environment). No means a **model** fault.

If all pass and the failing command points at a specific defect, it is an **implementation** fault. If commands fail for reasons unrelated to the task (missing dependency, broken tool, flaky test), it is an **environment** fault; check that first because it makes everything else look broken.

## Layers and remedies

| Layer | Symptoms | Remedy | What the tool enforces |
|---|---|---|---|
| spec | reviewer and builder disagree what "done" means; output is correct but not what the human wanted; requirements conflict | stop, ask the human, fix PLAN.md, human re-approves | task is blocked until the human runs `unblock` |
| plan | task too big; hidden dependency; pieces pass alone but break together | split or reorder tasks, define the interface first | task is blocked until the human runs `unblock` |
| prompt | plausible but different behavior; constraints skipped; contradictory instructions | rewrite the card: one goal, explicit constraints, a worked example, a Do-not list | next `start` refused unless the card or context changed |
| context | invented files, APIs or names; forgot earlier decisions; quality drops late in a long session | rebuild a minimal context packet, use a fresh session, reload `.ai/` state | next `start` refused unless the card or context changed |
| environment | failures unrelated to the task; missing tools or dependencies; flaky tests | fix the environment, record the working commands | next `start` refused until `osr env-check` passes |
| model | skipped steps, placeholders, claims of success that tool output contradicts | shrink the task, tighten the card, switch model | next `start` requires a different `--model` |
| implementation | one specific, reproducible defect | fix that defect | nothing extra; attempt cap still applies |

## Graph-level failures

Sometimes every task is fine in isolation and the whole fails. That is neither a retry problem nor a prompt problem. It is a missing contract.

- Put function signatures, data shapes, error conventions and file formats in the PLAN's Interfaces section before any task starts, and give every task that touches a boundary the relevant contract as a context file.
- Add an **integration task** after dependent tasks. Its `verify:` should exercise the seam end to end (a test that calls A through B), not re-run unit tests.
- If integration fails, triage it as **plan** (interface was wrong or missing) unless a single side clearly violated a written contract, in which case reopen that task with `osr reset`.

## The retry rule

Every new attempt must differ from the last in at least one of: the task card, the context files, the model, the environment, the task's size. The tool checks this for the layer you named. If you cannot name anything that will differ, you do not understand the failure yet. Escalate to the human instead of spending another attempt.

After `max_attempts` (default 3) the tool blocks the task. Hitting the cap is information: the problem is almost never the fourth try.

## Worked examples

**Builder keeps importing `utils.formatDate`, which does not exist.** Question 1: the card never listed the real date helper, so the builder invented one. Layer: **context**. Fix: add the file that defines the real helper to `context_files`, start a new attempt.

**Reviewer says R2 FAIL; builder says it meets the requirement.** Question 4: the AC says "fast" with no number. Layer: **spec**. Fix: ask the human for a threshold.

**Unit tests for T3 and T4 pass, the app crashes on startup.** Tasks pass alone; contract missing. Layer: **plan**. Fix: define the config-loading interface, add an integration task.

**Same card on a stronger model passes first try.** Question 5 says **model**. Fix: switch model or split the task smaller for the weak one.
