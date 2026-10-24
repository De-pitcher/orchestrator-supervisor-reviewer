# Proposed baseline transition before T26

Status: prepared by the independent supervisor; awaiting human approval. No approve-plan/reset/signoff was executed for this transition.

T22, T23 and T24 have independent technical acceptance. T25 passed 36 independently executed focused tests, spec and quality review and closed at ledger 297 as osr.legacy-closure.v1: explicitly UNVERIFIED, no current requirement credit, no invented historical bindings. Its start predates freshness metadata. Missing pre-correction red capture for its last seven tests remains a disclosed process exception.

## Concrete changes ready for review
- Preserved the exact old plan and T22-T27 cards in .ai/archive/pre-baseline-transition/. activation.diff records the changes.
- Retired only the completed T22-T25 active cards; their state/ledger events and snapshots remain intact.
- T26 has no active-task dependency: its already implemented prerequisite code is adopted only as starting baseline content, not fresh verified requirement evidence.
- T27 depends on T26 and still maps every requirement R20-R25. No AC was removed or weakened; all current requirements must obtain fresh evidence before final acceptance.
- Updated live PLAN.md to explain the historical and active sequences. Remaining card context includes this transition and the current live plan. The original docs/evidence-hardening proposal remains a historical packet; .ai/PLAN.md and active cards control execution now.
- Source files, .ai/config.json, state, ledger and snapshots were not manually edited during this transition. Nothing was committed, pushed, released or globally synchronized.

## Human action
Review .ai/PLAN.md and .ai/archive/pre-baseline-transition/activation.diff, then run once from the project root:

```powershell
python scripts/osr.py approve-plan --by Sam
```

This binds the CURRENT governed tree into a new baseline. It approves the starting point; it does not certify correctness or promote old reviews. The approval command refuses while any task is active. No task is currently active. Never run it through the implementation agent or label agent execution as human execution.

After success, run osr next; expected action is start T26. The implementation agent may then start T26 and prepare failing commit-gate regressions with valid controls, stopping for independent red-test review before coding. It must not run review/done or human-only commands.

## Remaining acceptance
T26 must enforce audit --check and staged-byte parity without mutating the index/project. T27 must migrate the documented legacy fixtures without exemptions, run the complete discovered test inventory in sequential bounded batches on stable bytes, preserve benchmark attacks/canaries, document remaining limitations and obtain independent reviews and final audit. Remote CI is UNVERIFIED until executed. Local hooks remain bypassable and ledger tamper resistance still requires an external trust boundary.

Validation: plan-check passed (6 automatic requirements); task-check --all passed (T26, T27); ledger integrity passed and head remains 297. osr next correctly stops for human plan approval. No implementation tests were rerun for these planning-only changes.
