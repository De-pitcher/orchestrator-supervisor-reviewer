C1: PASS - Inspected the T24 diff and callers: terminal_test_name, extract_passed_tests, resolve_test_declaration and named_test_message are referenced by cmd_verify and gate_status only; the old xml.etree scan and inline testcase regex are gone; standard library only, Python 3.8-compatible syntax and % formatting.
C2: PASS - Missing retained log, digest mismatch, empty declaration, zero terminal matches, multiple terminal matches and nonzero command results all take explicit rejection paths; digest failure exits 4 with the offending log named, and no verify evidence is written from unverified bytes.
C3: PASS - Evidence selection is current-run only: no log-directory discovery, no XML reports, no substring/suffix matching, and failed commands cannot contribute names. Digest is checked before decode/parse, so replaced log bytes are rejected rather than interpreted.
C4: PASS - Full task delta inspected against the T24 start snapshot: two changed files, no placeholder or stub code, no truncated helpers, and no deleted historical tests. The 13 red assertions were replaced by real rejection paths, not skipped.
C5: PASS - tests/test_run_logs.py rerun green (bare `name ... ok` fixture lines still reach passed_tests); the verbose negative-test seam flow and review-pack flow in tests/test_osr.py rerun green. Quiet-runner legacy fixtures now fail closed and are recorded for T27 migration in .ai/reviews/T24.red.md, with no claim of complete release regression here.
C6: PASS - 16 focused tests: three green controls (activation extraction, supplied current text, in-project unambiguous short declaration through real start/verify) plus 13 attack cases driven through real cmd_start/cmd_verify subprocesses. Independent reruns reproduced 13 red then 16 green; formal verify run e4744d5ce5c64c50b1ea6ec7c237de9d passed in 8.8s.
C7: PASS - Helpers have explicit identity/ambiguity docstrings and match existing naming and structure beside gate_status; no new dependency, no shell parsing, no regex vocabulary for test families. Config, quick and review behavior are untouched except shared gate resolution.
C8: PASS - Actual diff against the T24 start snapshot is exactly scripts/osr.py and tests/test_test_evidence.py, both in allowed_files. No other source, card, config or documentation file was edited by this task.

BREAK_ATTEMPTS:
- Replaced the retained log of a real passing command with forged `test_required ... ok` bytes; the recorded digest no longer matched, verify exited nonzero and the forged name never entered ledger passed_tests.
- Ran a real command that prints `test_required ... ok` and exits 1; the name was excluded from passed_tests and the declared negative-test gate stayed failed.
- Declared `tests/test_param.py::test_add[gamma]` while output contained `[alpha]`; the parameterized identity did not match and verify failed, while the exact `[alpha]` declaration passed.
- Declared the short name `test_user` against AlphaTest.test_user and BetaTest.test_user; verify reported the ambiguity and exited nonzero, while both fully qualified declarations passed.
- Planted a stale `.ai/logs/*.xml` report claiming the declared names; extraction ignored the directory and both acceptance and negative-name gates remained unsatisfied.

VERDICT: PASS
