# Builder handoff and supervision contract

Prepared 2026-10-23 against HEAD 769b307 on v0.3.2, including existing uncommitted work. Start here. Read PLAN.md, then only the assigned card and its relevant source ranges. This packet addresses five reproduced defects; do not merge in the larger existing release roadmap.

## Activation: one planning checkpoint
The packet is deliberately inactive. Do not overwrite the live .ai workflow to make it run.

Before implementation, the supervisor prepares one concrete activation diff for human review:
1. Inventory existing modifications and active T0. Identify which changes are accepted baseline and which remain unfinished. Preserve old cards, plan and generated history; do not fabricate completion or approval. Use the normal human reset/reapproval path where required.
2. Reconcile this focused packet with the live plan in one edit: retain outstanding existing requirements or explicitly defer them with human agreement. Preserve task IDs; T22-T27 were unused when prepared. Do not approve an entire unrelated release merely to start these fixes.
3. Install the approved task cards into .ai/tasks and configure exact, narrow verification commands. Existing global_verify runs the entire suite; replace that policy only in the reviewable activation diff with sequential scoped commands and the final all-tests inventory described below. Until human reapproval, do not run formal verify with a quietly weakened configuration.
4. The monolithic scripts/osr.py exceeds the current 1500-line context budget. Propose context_budget_lines=6500 for these cards, retaining the 150-line card cap; source reading still uses bounded ranges. Do not extract permanent copied source just to evade the budget.
5. Avoid a confirmation/start deadlock: new regression modules do not exist, and failing regression commands cannot be confirmed. Prepare all five modules together with one meaningful existing-behavior clean control each (retained log digest; exact confirmed command; current unittest pass extraction; unchanged snapshot; no-workflow hook). These are baseline test fixtures, included in the activation diff for review, not a claim that any bypass is fixed. Register and actually confirm their exact commands once, then approve the config with the plan. Start each formal task from those green controls; add the failing attack tests after start, capture red output, then implement. start may record the green baseline; the later captured red run supplies the defect proof. Do not use allow_no_commands, executable-prefix acceptance, empty tests or fabricated confirmation. Later command changes require renewed confirmation and human config approval; do not churn commands between tasks.
6. Run plan-check and task-check --all. Human reviews and runs approve-plan; agents do not run human-only commands. If this migration conflicts with active T0, resolve it once before starting T22, rather than retrying start.

The exact skill instruction is in ../../SKILL.md: "Then stop and ask the human to review and run `osr approve-plan --by <name>`." Plan/config reapproval is the explicit gate, not an inferred permission request. This packet itself does not alter the live plan.

## One task per builder session
Builder responsibilities:
- Run osr next. If it requires a human action, report that once and stop dependent work. Do not loop on next or start.
- Read the assigned requirement, card, applicable instructions, and relevant functions from disk. Locate callers with rg. No repeated whole-repository dumps.
- Write meaningful failing tests first in the assigned regression module. Run only that module and record the exact failing assertions and command exit. A syntax/import failure does not prove the defect.
- Submit the red tests for supervisor inspection; then implement only the assigned scope. Do not write your own passing spec or quality review.
- Run focused tests while developing. At handoff run formal osr verify once on the final stable bytes, then osr review-pack. Provide evidence references and stop for review.
- Do not mark done, start the next task, commit, push, deploy, synchronize global skills, change versions, install dependencies, or create additional agents.

Supervisor responsibilities (this reviewing agent):
- Inspect red tests against the AC and clean control before implementation proceeds. Confirm they exercise the real gate rather than a mocked success/failure.
- Inspect the diff and files from disk, independently rerun the focused regression command, and inspect ledger/log digests. Treat existing OSR PASS as one check while the tool is being repaired, never as the sole oracle.
- Perform spec and quality reviews separately using the repository templates, real citations and three concrete break attempts. Record FAIL if reproduced behavior violates an AC.
- Record review through osr, then run done only after both reviews and stable verification pass. Release the next card explicitly. Review artifact writes are permitted to the supervisor, not the builder; keep builder code scope unchanged.

## Stop conditions and token discipline
- Maximum two unsuccessful implementation/verification cycles per card. Then stop with failure layer, exact evidence, and one changed approach. No repeated identical command, broad speculative refactor, or new task without review.
- A newly exposed defect outside scope goes in the handoff as BLOCKED or deferred; supervisor decides whether the card must change. Do not repair the whole roadmap opportunistically.
- Escalate immediately for an undefined interface, required out-of-scope file, approval gate, or unavailable runtime. Do not spend two cycles guessing.
- One progress update per meaningful result. Handoff at most 15 lines: task; changed files; red evidence; final command/exit/test count/log and run ID; known gaps; requested review. Use the transcript until a tool-managed handoff location is authorized.
- Rerun a successful unchanged check only for independent review or when later changes affect its assumptions. Do not run a standalone benchmark if the identical final-tree benchmark already ran in a batch.

## Validation and final acceptance
Commands use PowerShell and Python stdlib. Each card names a discoverable regression module, so missing tests cannot pass unnoticed. Tests are not implemented by this planning packet.

For final regression, enumerate actual unittest-discovered IDs (not text matches for def test), partition them into sequential bounded batches, and retain each batch's exact selected IDs, output, exit, runtime and final tree digest. Use subprocess timeouts. Module batching is allowed; split tests/test_osr.py by discovered method IDs so no one command launches the full suite. Expensive existing benchmark methods may share a process/cache, but no discovered ID may disappear. Demonstrate the union equals the discovered inventory with no duplicates; adding a collection-only test is not required. CI can run the existing matrix in its normal environment; do not claim remote success without output.

Current analysis evidence: 22 selected tests passed on Windows/Python 3.14.3; plan-check and ledger-verify passed. The full suite and remote CI were not run in that analysis. Do not reuse this as implementation proof.

Final acceptance requires all R20-R25 ACs, clean controls, independent reviews, current-byte audit, staged-index hook controls, and the complete batched test inventory. Preserve benchmark scenarios; changes to fixtures for strict exact command confirmation must retain their original behavioral purpose. Historical tests that intentionally demonstrate vulnerabilities must be examined and explicitly migrated to rejection assertions when their defect is fixed.

Until T25/T26 are accepted, independently compare final hashes and demonstrate each attack rejection; the known-vulnerable audit and commit hook cannot certify their own repair. Cross-platform behavior beyond executed environments is UNVERIFIED pending CI. A missing run or human decision stays pending; never substitute a claimed success.
