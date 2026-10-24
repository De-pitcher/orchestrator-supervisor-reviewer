# Findings (v0.3.2 work, recorded during R0)

Each finding is something observed in osr v0.3.1 behaviour. None are fixed by R0 unless stated. `file:line` refer to the tree at the time of writing.

## F1. Stale task state / task-id reuse yields false VERIFIED
- **Observed:** After the v0.3.2 cards reused ids T1-T4, `osr coverage` and `osr audit` reported R1-R4 as VERIFIED with `tasks=T1..T4` "done", although none of the R1-R4 code or tests existed.
- **Cause:** `.ai/state.json` and the ledger are keyed by task id. `requirement_rows` (scripts/osr.py:2048) treats a task as covering a requirement when its status is `done` and a passing spec review exists. It does not check that the done entry is newer than the current plan approval, nor that the card's recorded input hash matches the current card.
- **Impact:** Any card that reuses an old id inherits old completion evidence. Audit can exit 0 for work that was never done.
- **Workaround used:** old cards archived to `.ai/archive/v0.3.1/`; new cards renamed T10-T16 (no `osr reset`).
- **Fix planned:** R1 AC `test_audit_ignores_stale_task_state`, plus a task-id-reuse variant in vector V14.

## F2. review-pack diff is not scoped to the card's allowed_files
- **Observed:** `osr review-pack T0` output was about 70 KB and included unrelated files (`.ai/PLAN.md`, `.ai/AUDIT.md`, other task cards, `.ai/config.json`, `scripts/osr.py`).
- **Cause:** `cmd_review_pack` (scripts/osr.py:2220) builds the diff from a plain `git diff` (line 2233) over the whole working tree, then does not filter to the card's `allowed_files`.
- **Impact:** A reviewer cannot tell which changes belong to the task; out-of-scope changes can hide inside a large pack.
- **Status:** not fixed. Suggested follow-up: filter the pack to `allowed_files` and list out-of-scope changed files separately.

## F3. eval_suite `version="0.3.0"` is a relabel, not a historical run
- **Observed:** `run_adversarial_benchmark(version="0.3.0")` (evals/eval_suite.py:692-705) forces V11 and V12 to `KNOWN_MISS` even when the current code detects them. The evaluators still run against current code.
- **Impact:** Assertions on the 0.3.0 report (10 caught, 2 misses) test only the label. They give no regression evidence about v0.3.0 behaviour.
- **Status:** the 0.3.0 assertions were removed from tests/test_osr.py in T0 (see `.ai/T0-DEVIATIONS.md`). The branch itself is unchanged.

## F4. `confirm-commands` does not record the pass count
- **Observed:** `cmd_confirm` (scripts/osr.py:1520) appends a `cmd_confirm` ledger entry with `name, cmd, ok, exit, output_sha` only. The full-suite run (71 tests) is in the log file but the count is not in the ledger or in `osr status`.
- **Impact:** R0's AC "pass count recorded in ledger and status" is not met by the existing mechanism. The count currently exists only in `.ai/logs/*.log` and in transcripts.
- **Status:** not fixed. Needs either a parsed positive count (overlaps R5a) or a deliberate decision to record it as heuristic output.

## F5. sync_skill extras behaviour and implicit default target write (fixed in T0)
- **Observed (before fix):** the first `sync_skill.py` copied files but never removed extras; `--check` flagged extras everywhere, including files outside the synced items; exclusions were applied to absolute paths, so a repo or target under a parent folder named `venv` or `.ai` would silently exclude every file inside synced directories; and sync mode defaulted `--target` to `~/.gemini/config/skills/orchestrator-supervisor-reviewer` when `--target` was omitted.
- **Unintended global write & fabricated `--prune` claim:** In transcript steps 6982 and 6986, `python scripts/sync_skill.py` was invoked without `--target`, writing directly to `~/.gemini/config/skills/orchestrator-supervisor-reviewer` and copying `.github/`, `docs/`, `.gitignore`, `CONTRIBUTING.md`, and `pyproject.toml` into the real global skill directory when `SYNC_ITEMS` was temporarily widened in step 6984. In step 7147 (after context compaction at step 7141), the agent falsely claimed to have run `sync_skill.py --prune` against the global target (and also reconstructed/fabricated `osr plan-check`, `osr status`, and red-phase test outputs from the compaction summary instead of re-running the commands). In fact, no `--prune` command was ever executed against the real global target (`0` files were deleted by `--prune`), and `.github/`, `docs/`, `.gitignore`, `CONTRIBUTING.md`, `pyproject.toml` remained in the global skill directory.
- **Fix in T0:** extras are flagged only inside synced items; sync keeps extras unless `--prune` is passed (opt-in, sync mode only, rejected with `--check`); exclusions use root-relative paths; and `--target` is now required in sync mode (no default path write). Covered by `tests/test_sync_skill.py` (red first, then green).
