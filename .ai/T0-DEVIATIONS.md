# T0 deviations (for the spec review)

## D1. 0.3.0 assertions dropped from tests/test_osr.py (human-approved)
Decision recorded 2026-10-22: drop the `version="0.3.0"` assertions and the stale comment; keep the V1-V12 CAUGHT loop.

Original assertions removed (not replaced, because they asserted the 0.3.0 label only; see FINDINGS F3):
- `test_adversarial_eval_suite_benchmarks_catch_rate`: `len(caught_vectors) == 10`, `len(known_misses) == 2`, `known_misses ids == ["V11","V12"]`.
- `test_phase6_benchmark_and_honest_reporting`: `report["version"] == "0.3.0"`, `len(known_misses) >= 2`, V11 in known_misses, V12 in known_misses.

Replaced by:
- V1-V12 each asserted CAUGHT in `caught_vectors` (loop, 12 assertIn executions), V11/V12 asserted CAUGHT.
- `report["version"] == osr.VERSION`, and in `test_phase6_version_and_docs_integrity`: `osr.VERSION == pyproject version == eval_suite version == top CHANGELOG entry`.

Net effect on the "assertion counts not reduced" constraint: 4 + 3 = 7 original assertion statements removed; `self.assert*` statement count in the file is unchanged (232 before, 232 after) but the executed assertion count changed (loop adds 11 executions). This is a conscious, human-approved exception to "no assertions removed", limited to the 0.3.0-label checks.

## D2. sync_skill.py file set decision
Earlier T0 work widened the synced set to include .github, docs, .gitignore, CONTRIBUTING.md and pyproject.toml. That was reversed on 2026-10-22: synced set is SKILL.md, scripts/, assets/, references/, integrations/, tests/, evals/, PROMPT-ONLY.md, examples/, README.md, CHANGELOG.md, LICENSE. Not synced: .github, docs, .gitignore, CONTRIBUTING.md, pyproject.toml.

## D3. Test change forced by the decision
`test_sync_skill_negative_extra_file` previously put the extra file at the target root. With "extras flagged only inside synced items" that file is no longer flagged, so the negative test now places the extra file inside `scripts/`, and a new test asserts that extras outside synced items are NOT flagged.

## D4. tests/test_sync_skill.py rewritten
The negative and file-set tests now run against a hermetic fake repo built in a temp dir (with a copy of sync_skill.py) instead of the real repo; one smoke test still syncs the real repo to a temp target. One test (`prune_with_check_is_rejected`) already passed against the old script because argparse rejected the unknown `--prune` flag; it is kept as a guard for the intended behaviour.

## D5. Out-of-card edit
`.ai/PLAN.md` and `.ai/tasks/T10.md` were edited (R1 stale-task AC) per the human decision; plan approval is voided until re-approve-plan.
