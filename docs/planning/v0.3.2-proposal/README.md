# v0.3.2 planning approval packet

Status: PROPOSED / NOT APPROVED. This directory is a review artifact only. The active `.ai/PLAN.md`, `.ai/tasks`, config, ledger, state and implementation remain unchanged, including all prior uncommitted edits. No feature tests, supervisory operations, synchronization or publication were performed.

## Artifacts
- [Revised plan](PLAN.md)
- [Concrete planning diff](planning.diff): compared with the actual working files read at session start, including uncommitted content, rather than older HEAD planning content.
- Proposed cards: [T0](tasks/T0.md), [T10](tasks/T10.md), [T17](tasks/T17.md), [T11](tasks/T11.md), [T12](tasks/T12.md), [T13](tasks/T13.md), [T14](tasks/T14.md), [T15](tasks/T15.md), [T16](tasks/T16.md), [T18](tasks/T18.md), [T19](tasks/T19.md), [T20](tasks/T20.md), [T21](tasks/T21.md).

## Decisions awaiting the operator
| Decision | Proposed choice |
|---|---|
| D1: baseline dependency/ownership | Move normalized positive counts from T0 to T15; T0 retains captured full-suite output/exit and explicitly owns the existing requirement-ID parser edit plus behavioral tests. Preserve prior deviations D1-D4. |
| D2: legacy evidence | Current requirements relying on unclassified legacy evidence yield UNCLASSIFIED-LEGACY/exit 2; unrelated history remains disclosed without permanently blocking fresh evidence. Never rewrite ledger bytes. |
| D3: unprotected compatibility | Retain explicit compatibility mode with warnings; recommend audit exit 2 when current approvals are unprotected. Protected mode requires the new mechanism. |
| D4: command authority | Exact confirmed strings; separately confirm approved variants, with no interpreter-wide authorization. |
| D5: test-first/review | Batch focused failing-test approval before implementation; use fresh reviewers, label same-model reviews honestly under current config. |

These choices alter acceptance or security policy and remain proposals. No checkbox or successful structural check records human approval. The actual Antigravity assessment (T12), pinned baseline selection (T19) and explicit installation destination (T21) remain later evidence/input gates.

## Validation and preservation
Both commands ran using an unchanged copy of the current CLI and actual config/ledger in a disposable project with the proposed plan/cards overlaid. No dummy successful confirmations, relaxed budgets or modified settings were introduced. Paths in cards intentionally refer to their eventual active locations; the proposal is not an executable active task set.

- `python scripts/osr.py plan-check`: exit 0, 13 requirements, one manual. [Complete output](plan-check.log).
- `python scripts/osr.py task-check --all`: exit 0, all 13 cards OK. [Complete output](task-check.log).

These commands are structural validators, not feature tests or evidence of implementation correctness. Relevant source functions and bounded reads are named in each card; the full CLI exceeds the context budget and is deliberately not included as an entire context file. Proposed new regression names are explicitly future tests.

T11 now covers CLI/status, Stop, PreToolUse, hook config and focused tests. T13 covers pre-tool protection and isolated fixture migration. T17-T21 add explicit command authorization, review boundaries, integration/baseline validation, release preparation and installed parity. IDs T17-T21 were checked against current/archive cards and ledger ownership and were unused. Dependencies serialize shared CLI edits.

Every pre-existing non-Git, non-cache file was hashed before preparation and rechecked afterward; no bytes changed. Generated Python caches were excluded. The check includes pre-existing untracked files, active governance and implementation. No active task was started or closed.

## Next required action
The operator reviews the diff and resolves D1-D5. If accepted, a separately authorized promotion must reconcile these proposed files into active planning while preserving concurrent work; rerun structural checks there before the real operator approves that actual plan. Do not approve the existing active plan as though it were this proposal. No promotion is performed in this session.

Human-only approval comes from [SKILL.md Iron Rule 10](../../../SKILL.md) and [repository Iron Rule 10](../../../.agents/rules/osr-iron-rules.md); test-first approval comes from [ROADMAP.md](../../../ROADMAP.md). They reserve supervisory operations to the operator. Preparing this packet requires no approval.

Preparation source HEAD: `769b3071486b91315b4529e9749152b3e7ac7559`; this includes an already dirty working tree and is not a claim of clean revision identity.
