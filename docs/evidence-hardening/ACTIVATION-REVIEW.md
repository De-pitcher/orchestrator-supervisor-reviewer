# Activation review, 2026-10-23

Verdict: activation corrections accepted after independent recheck. Ready for human T0 reset and plan approval. No production implementation or formal task review is accepted by this document.

## Correction recheck
- Reconstructed the previous plan from the old/context lines of the active/.ai/PLAN.md hunk in planning.diff. The archived plan matches that source exactly after newline normalization. Both reported LF and raw CRLF SHA-256 hashes match. The separate transcript provenance claim was not independently inspected and is not needed for this result.
- Both archived T0 snapshot copies match the still-present live snapshot byte for byte.
- The live plan now states that the packet is installed into .ai.
- Ledger integrity passes; its head remains sequence 229, cmd_confirm. T0 remains in_progress; no reset or new approval was fabricated.
- No additional test runs or command confirmations were needed for these archive/document corrections. The initial independent checks below still describe the unchanged test controls.
- Human now runs reset T0 with the deferral reason, then approve-plan. This authorizes only starting T22 and submitting its failing regression tests for review; implementation follows the red-test review checkpoint.

## Independently verified
- All six installed cards match the proposed cards exactly as decoded text.
- plan-check: exit 0, six automatic requirements.
- task-check --all: exit 0, T22-T27 valid.
- ledger-verify: exit 0. Five new confirmation entries, sequences 225-229, record exact configured commands and success.
- Each of the five baseline control modules was rerun sequentially: one test each, all passed.
- Confirmation log files exist. Their output hashes reconcile after reversing the existing Windows text-mode newline translation. This is not proof of raw-byte identity; see T22 note below.
- Current scripts/osr.py diff still contains only the preexisting requirement-ID parser change; no evidence-hardening implementation is present there.
- allow_no_commands remains false. Empty global_verify is the explicitly proposed scoped-testing policy, subject to human approval and T27 complete-inventory acceptance; it is not full-suite verification.

## Original activation findings (archive/document corrections resolved above)
1. Resolve the orphan active T0. state.json still records T0 in_progress while its card is no longer in .ai/tasks. This is not optional housekeeping: pre_tool.py selects the first in_progress state entry, sees no T0 card and allows the edit without checking T22's scope. The status report hides T0 because it enumerates only current card files. Human must use the existing reset command with an explicit deferral reason before starting T22; do not edit state.json manually. Reset retains ledger history but removes the old snapshot, so preserve the existing T0 snapshot as a clearly labeled historical copy before asking the human to reset it. No hook redesign is requested in this correction.
2. Preserve the superseded live plan or disclose its loss accurately. .ai/archive/deferred contains T0 and T10-T16 cards, but no PLAN.md. Archive the actual pre-activation live plan from the workhorse's pre-edit copy/local history, along with its origin and hash. The existing docs/planning/v0.3.2-proposal/PLAN.md is a separate larger proposal and must not be relabeled as the previous live plan. If the exact previous content is unavailable, report that explicitly for the human's acceptance; do not reconstruct an allegedly exact archive. Also update the new live plan's stale assumption that the packet remains entirely staged outside .ai.

## T22 red-test requirement, not additional activation scope
The baseline log control reads with read_text(), which normalizes line endings; it proves textual retention, not retained-byte digest identity. Actual confirmation logs contain CR-CR-LF sequences and their raw SHA-256 differs from recorded output_sha. In T22, include raw read_bytes() versus recorded output_sha tests for LF, CRLF, Unicode and failed command output, alongside same-label/frozen-time collision tests. Choose one explicit output encoding/newline contract and preserve it through writing and later extraction. Do not weaken assertions to accept either hash. This implements R20's existing exact-output contract.

## Next checkpoint
Human runs reset T0 with the recorded deferral reason, then approve-plan. The skill reserves both commands for the human. After approval, builder may start T22 and submit failing regression tests for supervisor inspection before implementing the fix. No T23 advance is authorized.
