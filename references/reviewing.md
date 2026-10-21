# Reviewing well

The reviewer's job is to find what is wrong, not to confirm what is right. A review that cannot fail is not a review. The tool makes lazy reviews hard to submit; this file explains how to make a good one.

## Contents
- Ground rules
- Spec review
- Quality review
- Break attempts
- Reviewer independence
- When the review says FAIL

## Ground rules

- **Review the files on disk, not your memory or the builder's summary.** Open every changed file. `osr verify` lists them.
- **Start by assuming it is wrong.** You are looking for the specific line that proves otherwise.
- **Evidence or it did not happen.** Every PASS in a spec review quotes real code. The tool opens the file and checks the quote is within three lines of the line you cited, so a made-up citation is rejected.
- **One pass cannot see everything.** Say what you did not check. Use UNVERIFIED for that.

## Spec review

Goal: does the code satisfy each requirement's acceptance criterion?

For each requirement of the task:
1. Reread the AC in PLAN.md (not the card's paraphrase).
2. Find the code that implements it and the test that exercises it.
3. Ask: what input would violate the AC? Is it handled?
4. Write `R#: PASS @ path:line "exact snippet"`, or `FAIL - reason`, or `UNVERIFIED - reason`.

Use UNVERIFIED when the criterion needs judgment a machine cannot make (look, feel, tone), when it needs a runtime you cannot run, or when you are not able to confirm. Requirements marked `Check: manual` in the plan can only be UNVERIFIED. This is not failure; it routes the item to the human honestly.

Evidence line format, exactly:

```
R1: PASS @ src/calc.py:3 "return a + b"
```

The snippet must be copied from the file. Whitespace differences are ignored.

## Quality review

Goal: is the code sound beyond meeting the letter of the requirements? Eight checks, each answered PASS, FAIL or NA with a note naming what you actually inspected.

- **C1 references exist.** For every import, called function, config key, env var, CLI flag, endpoint or file path in the changed code, find where it is defined. This catches the most common AI failure. The tool already checks Python and JS/TS imports; you check the rest.
- **C2 error handling and edges.** Empty, null, huge, malformed, concurrent, offline, timeout.
- **C3 security.** Untrusted input reaching a shell, query, file path, template or HTML; secrets in code; authorization on new endpoints; unsafe deserialization.
- **C4 no placeholders or dead code.** Stubs, TODOs, commented-out blocks, debug prints, unused additions.
- **C5 no regressions.** Search for callers of anything whose signature or behavior changed.
- **C6 tests are meaningful.** They assert behavior, would fail if the code were wrong, are not skipped, were not weakened. A test that cannot fail is worthless. Mentally break the code and see whether a test notices.
- **C7 conventions.** Naming, structure, error style match neighbouring code.
- **C8 scope.** Only what the card asked changed.

A note like "looks good" is rejected for being short, and it would be useless anyway. Write what you looked at: "grepped all 4 call sites of `parse()`; none pass the removed argument".

## Break attempts

Write at least three concrete ways the code could fail, each at least 25 characters, as bullets under `BREAK_ATTEMPTS:`. Good ones name an input and an expected failure mode. Bad ones restate a checklist item. If you cannot think of three, you have not understood the code well enough to approve it. Consider: boundary values, hostile input, order of operations, repeated runs, partial failure, time, locale, large data, concurrency, platform differences.

You do not need to run them, but if one is cheap to run, run it. A reproduced failure is a FAIL.

## Reviewer independence

A model reviewing its own work in the same context tends to confirm it. In order of strength:

1. A different model, fresh session, sees only the card, the diff and the plan.
2. The same model, fresh session, sees only the card, the diff and the plan.
3. The same model, same session: switch hats explicitly and reread the files from disk.

The tool records which one you used (`--model` on start, `--reviewer` on review) and flags self-review in the audit. Set `"require_distinct_reviewer": true` in config and the tool refuses a review whose `--reviewer` name equals the `--model` that implemented (it compares names, so use distinct names for distinct models or sessions).

## When the review says FAIL

The failure is recorded and counts toward the attempt's failure limit. Fix the code, run `osr verify` again, and write a **new** review of the current code. A review file identical to one already recorded is refused, so you cannot resubmit an old approval. If you hit the limit, triage (`references/failure-triage.md`).
