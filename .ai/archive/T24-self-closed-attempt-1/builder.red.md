# T24 red-test review

Decision: red reproduction accepted; implementation may proceed in `scripts/osr.py` and `tests/test_test_evidence.py` only. This is not a formal spec/quality PASS or completion.

## Independent execution

`python -m unittest discover -s tests -p test_test_evidence.py -v` -> 16 tests, 13 failures, 0 errors, 3 passes, exit 1, 6.0s; a second run reproduced 16/13/0/3. Raw output: `.ai/reviews/T24.red-run.txt`. Task delta against the T24 start snapshot is only `tests/test_test_evidence.py`; `scripts/osr.py` is unchanged for this task. Ledger integrity passes; T24 is attempt 1, failures 0. No formal `osr verify` was run at this checkpoint.

## Confirmed red evidence (real gates, real subprocess output)

- Stale XML: `extract_passed_tests` returns `test_stale_only` from `.ai/logs/*.xml` alone. End to end, verify exits 0 and records the stale name from current output `test_alpha`, satisfying a declared negative test and the acceptance gate it never ran in.
- Log-hash tampering: after a real passing command, replacing its log bytes with forged `test_required ... ok` output makes verify record `test_required` as a pass; the recorded `output_sha` no longer matches the file.
- Failed commands: a real command that prints `test_required ... ok` and exits 1 still lands `test_required` in ledger `passed_tests`.
- Suffix collision: `test_missing_user_extra` satisfies the declared `test_missing_user`, and verify passes.
- Ambiguous short names: two qualified tests ending in `test_user` are collapsed; verify prints "Negative tests verified: test_user" and exits 0.
- Qualified identity: exact `test_sample.SampleTest.test_alpha` is not extractable at all (only the short name is kept); exact pytest `test_mod.py::test_case` collapses to `test_case`, so `tests/test_param.py::test_add[alpha]` is indistinguishable from `[gamma]` and verify accepts the wrong parameter.
- Missing negative tests: verify prints a warning but exits 0 (`test_absent_negative` never ran). This is the R22 defect "not merely warn".

## Controls that pass today (must stay green)

- Activation clean control: current unittest verbose output yields its passing tests.
- Supplied current text still parses (`test_fresh ... ok`).
- In-project unambiguous short declaration (`test_alpha`) passes verify with exit 0 and all three gates.

## Compatibility inspection (DoD)

- `tests/test_osr.py:1233` declares a negative test and currently tolerates verify passing while it is absent. Under the new rule that inner `osr verify` fails (the test ignores that exit). Part 2's reviews are only attempted after verify; they are not recorded on failure, then part 3 writes the real negative test, re-verifies on current bytes and records fresh reviews. The `done` assertion (`nonzero` and "negative test" in output) remains valid. No fixture command change is needed.
- `tests/test_run_logs.py:415` asserts bare fixture lines `test_alpha ... ok` / `test_beta ... ok` reach ledger `passed_tests`. The parser must keep accepting an unqualified `name ... ok` as its own identity (no XML scan, no digest bypass).
- `tests/test_hardening_hypotheses.py:442` (H7) runs real verbose unittest output including the declared negative test. Exact identity keeps it passing; its intentionally vacuous assertion is a separate open hypothesis, not T24.
- No existing test relies on XML-directory discovery or on substring suffixes except the legacy behavior above; no test file or configured command will be changed.

## Implementation release

1. Make `extract_passed_tests` text-only. Delete the `.ai/logs/*.xml` directory scan; no mtime guessing and no XML report acceptance (an XML-only runner must surface current stdout or report missing named evidence).
2. Parse canonical identities: unittest `method (module.Class.method)` -> `module.Class.method`; unqualified `name ... ok` -> `name`; pytest node ids keep `file::Class::test[param]` including the parameter suffix; keep PASSED/tick forms. No substring or suffix vocabulary.
3. In `cmd_verify`, hash-check every recorded log against its own `output_sha` before use; a missing or mismatched log is an integrity failure (exit 4) and never evidence. Extract only from results whose command succeeded.
4. Resolve declarations exactly: a qualified declaration matches only the identical canonical id; a short declaration matches only when exactly one current qualified id has that terminal name; zero matches report "did not run and pass"; multiple matches fail with a diagnostic that includes "ambiguous" and the candidates.
5. A missing/ambiguous declared negative test sets verify `ok=False` (exit 2) in addition to failing `gate_status`. Acceptance and negative gates use the same resolver, replacing substring checks. Do not synthesize passes or reinterpret failed-command output.
6. Preserve quick as non-formal evidence and keep the valid current-run controls. No new dependency.

## Stop

Focused module green, then formal `osr verify T24` once on stable bytes, then separate spec and quality reviews. Do not start T25.

## T27 fixture migration notes (green compatibility check)

- `tests/test_hardening_hypotheses.py::test_h7_negative_tests_semantic_vacuity` becomes red with T24 for the right reason: its project runs unittest with `-q`, so no test names exist in current output, and the declared negative test can no longer be "verified". R22 requires reporting missing named evidence rather than inventing it. T27 must change that fixture's verification command to verbose (`-v`), preserving the original vacuity hypothesis (a named test that runs with `pass` and no assertion). Do not restore quiet-output pass-through or substring matching.
- `tests/test_hardening_hypotheses.py` H1/H3/H4/H5/H8/H9/H10 and `tests/test_zero_runner.py` were already red before T24: their `start`/`verify` paths stop at pre-existing card/authorization validation (for example "Task T1 is 'todo'" and unconfirmed exact commands), or they assert pre-v0.3.1 hardening behavior. T24 code never ran in those failures. They stay in the T27 migration inventory; no T24 scope widening.
- `tests/test_osr.py::test_negative_tests_enforced_per_seam...`, `test_review_pack_includes_adversarial...`, `tests/test_run_logs.py`, and H7's non-quiet peers were rerun and pass, so the exact-identity change does not break the intentional verbose negative-test flow or the bare-name log fixture.
