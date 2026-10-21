# Walkthrough: adding `add()` to a tiny Python project

A real run of the tool (output trimmed). Plan: R1 `add` returns sums (auto), R2 docstring wording (manual).

```
$ osr init
$ osr detect
$ osr confirm-commands
=> test: CONFIRMED
$ osr approve-plan --by human
Plan approved by human. Any later edit to PLAN.md voids approval until re-approved.

$ osr start T1 --model model-a
Task T1 started (attempt 1). Allowed files: src/calc.py, tests/test_calc.py

# ...builder writes src/calc.py and tests/test_calc.py...

$ osr verify T1
Changed files: 2
  A src/calc.py
  A tests/test_calc.py
CHECK: PASS
$ python -m unittest discover -s tests -t . -q      -> Ran 2 tests ... OK   [exit 0]
$ python -m unittest tests.test_calc -q              -> Ran 1 test ... OK    [exit 0]
VERIFY: PASS
NEXT: Write .ai/reviews/T1.spec.md ...
```

Spec review file (`.ai/reviews/T1.spec.md`):

```
R1: PASS @ src/calc.py:3 "return a + b"
R2: UNVERIFIED - a human must judge the docstring tone

VERDICT: PASS
```

```
$ osr review T1 spec --reviewer model-b
REVIEW RECORDED: spec PASS
$ osr review T1 quality --reviewer model-b
REVIEW RECORDED: quality PASS
$ osr done T1
  [x] verify
  [x] review-spec
  [x] review-quality
Task T1 DONE (attempt 1).

$ osr audit
| R1 | auto   | T1 | VERIFIED      | src/calc.py:3 |
| R2 | manual | T1 | PENDING-HUMAN |               |
AUDIT: COMPLETE WITH HUMAN REVIEW PENDING for: R2

$ osr signoff R2 --by human --note "read it"
$ osr audit
AUDIT: PASS (every requirement has machine evidence or human sign-off)
```

## Things the tool refuses (all covered by tests)

- Starting before the human approves the plan, or after PLAN.md changed.
- Editing a file outside `allowed_files` (`SCOPE VIOLATION`).
- Importing a package that does not exist (`UNRESOLVED REFERENCE`).
- Adding "rest of the code unchanged" (`placeholder` flag).
- A review quoting code that is not in the file (`snippet not found`).
- Marking a `Check: manual` requirement as PASS.
- Editing code after the review (`NOT DONE`, stale review).
- A third blind retry (`Blind retries are blocked`), a restart without triage, and a "prompt" triage whose card did not change.
- A hand-edited ledger (`LEDGER INTEGRITY FAILURE`).
