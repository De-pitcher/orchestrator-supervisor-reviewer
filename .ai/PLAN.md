# Plan: close five reproduced evidence-integrity defects

## Goal
Make current-code completion, command authorization, test evidence and commit checks reject the five bypasses reproduced in the repository analysis on 2026-10-23. T22-T25 have independent technical acceptance under the historical epoch. The remaining active tasks are T26 and T27. This transition proposes a new human-approved starting baseline; it does not promote historical reviews into current requirement evidence. T27 must freshly verify and review R20-R25. The broader v0.3.2 release roadmap remains deferred.

## Non-goals
- The broader v0.3.2 roadmap (deferred requirements R0, R1, R2, R4b, R4, R3, R5a, R5b), new evidence classes, password redesign, hook protocol redesign, new language parsers, packaging, global skill synchronization and release publication.
- General resistance to an actor who can rewrite the tool, state and ledger together. External trust anchors remain necessary.
- Refactoring the monolithic CLI, adding dependencies, deleting historical ledger records, changing runtime compatibility below Python 3.8, or modifying existing user work without accounting for it.

## Deferred Roadmap Requirements
The following v0.3.2 release roadmap items and their cards (T0, T10-T16) are preserved in `.ai/archive/deferred/` and deferred pending completion of evidence hardening:
- Deferred R0: Repair test suite baseline & sync global skill copy (task card T0)
- Deferred R1: Evidence classes in the ledger and audit (task card T10)
- Deferred R2: Stop hook correctness and loop guard (task card T11)
- Deferred R4b: Antigravity agent terminal interactive prompt assessment (task card T12)
- Deferred R4: Approval secret unreadable by agent (scrypt & terminal prompt) (task card T13)
- Deferred R3: Harden quick path (task card T14)
- Deferred R5a: Positive test counts and new test execution (task card T15)
- Deferred R5b: Assertionless tests, selection flags, and extra tautologies (task card T16)

## Requirements
- R20: Preserve every verification command's output independently.
  - AC: Two commands with the same label and timestamp produce distinct immutable log files; each recorded output_sha matches its own complete log, including repeated and concurrent writes. Failed commands retain output too.
  - Check: auto
- R21: Authorize the exact confirmed command.
  - AC: An exact successful confirmed command passes; another script, module, argument list, executable, shell chain, or redirection does not inherit its authorization. No confirmed commands means rejection unless explicit allow_no_commands compatibility mode is enabled.
  - AC: Card verify, conformance, fixture-capture and quick use the same authorization rule; quick also checks ledger integrity and rejects weak/trivial commands. Changing an approved command requires confirmation and human plan/config reapproval.
  - Check: auto
- R22: Bind named test passes to the current command run.
  - AC: Old or unrelated XML files cannot satisfy current acceptance or negative-test gates. Logs used for extraction are hash-checked. Exact qualified identity matches; substring or suffix collisions cannot satisfy a different test. Ambiguous short names fail with an actionable diagnostic.
  - AC: Names from failed commands do not count as passes. Current unittest and pytest output controls pass; missing named negative tests make verify fail, not merely warn. Quick cannot create formal task evidence.
  - Check: auto
- R23: Audit the current accepted artifact set, not historical done flags.
  - AC: A clean completed workflow audits successfully; post-completion modification, addition or deletion of a governed file, changed card or config, reused task ID under a new approval, or missing completion manifest fails with an explicit stale-evidence reason.
  - AC: Two sequential tasks, including a legitimate later edit of the same file, can both complete and audit successfully. Editing files before starting the second task cannot launder an unreviewed change into its baseline. An edit during verification cannot receive approval without verification of the final bytes.
  - AC: Legacy ledger chains remain readable and unchanged; legacy completion evidence lacking freshness metadata is reported as UNVERIFIED with nonzero audit exit. audit --check performs the same checks without writing project files. A repeated unchanged audit does not rerun test commands.
  - Check: auto
- R24: Reject commits without current evidence for the staged artifact.
  - AC: The Git hook rejects incomplete tasks, stale completion evidence, scope drift, broken ledger integrity, missing tooling in an initialized workflow, and staged content different from the audited working file. A fully verified staged workflow passes. Partial staging cannot commit an older unverified version while a verified version exists only on disk.
  - AC: The check reads the index without modifying it, handles paths with spaces, and permits a repository with no OSR workflow. Hook execution does not append evidence, alter audit artifacts, run builders or invoke itself recursively.
  - Check: auto
- R25: Prove integration without hiding regressions or overstating claims.
  - AC: One focused regression module per defect demonstrates failing behavior before its fix and passing behavior after, with a valid clean control. Existing tests remain present and meaningful. Any incompatible fixture command change is explained and reviewed, not replaced by an exemption.
  - AC: Sequential test batches cover every discovered test ID exactly once in the final validation inventory; all batches exit zero. Existing benchmark vectors and canaries pass once on the final unchanged tree. README and guarantees explain strict confirmation, stale legacy evidence, index checks, and the remaining trust boundary.
  - Check: auto

## Interfaces and invariants
These contracts are fixed for this packet. Internal helper names may differ; changing observable policy requires supervisor review before implementation proceeds.

1. Run evidence: allocate a unique run_id and an exclusive-created log per executed command. Record run_id, log, output_sha, command and exit result. Never overwrite a previous log. Test parsing consumes the recorded output for that run after checking the digest. Do not scan the log directory for reports. XML discovery support is deferred: an XML-only runner must produce supported current stdout or report missing named evidence; never silently accept historical XML.
2. Authorization: exact trimmed command string matching against successful ledger-backed confirmation. Do not implement shell equivalence or executable-prefix permission. Confirm exact narrow commands before approving a plan. Explicit allow_no_commands retains its documented compatibility escape; it is not proof of confirmation. Check all call sites of is_verify_cmd_confirmed; quick must not have a separate permissive path.
3. Test identity: parse a runner-specific canonical qualified ID. Match qualified declarations exactly. A short declaration is accepted only if exactly one current qualified test has that terminal name. Preserve parameter identities; unsupported forms fail named-evidence gates explicitly. No substring matching. Do not turn a missing negative test into a successful verify record.
4. Freshness: capture a governed-tree baseline at plan approval and task-start checkpoint; completion records carry the exact accepted path-to-content-hash manifest, approval epoch, card digest and config digest. Represent deletion explicitly. Use the existing governed-tree ignore policy, record its config digest, and bind task cards separately because .ai is ignored. A whole-tree digest alone is insufficient unless unreviewed baseline drift is also rejected.
5. Acceptance ownership: derive the current accepted manifest from the approved baseline plus chronological, valid completed-task deltas. Every accepted delta must have matching verification and both reviews for those bytes. Later reviewed tasks may supersede earlier content on overlapping paths. Before starting a subsequent task, reject unexplained drift from the previously accepted manifest. Permit only one active task in this scope. Keep recovery changes visible to the active task; do not silently resnapshot them. Historical done flags are never sufficient evidence.
6. Test-time writes: if governed content changes between pre-run and post-run verification snapshots, fail verification and require another run on stable bytes. Audit checks freshness without executing configured commands; missing metadata fails closed with actionable migration guidance. One new approved baseline and freshly verified/reviewed tasks establish the new evidence epoch; do not synthesize old approvals.
7. Commit gate: use audit --check for current workflow evidence, then compare index bytes with audited working bytes for every staged path (including staged governance files). Handle deletions and additions. Require the baseline OSR governance files to be tracked or staged for an initialized workflow. Do not compare Git object IDs directly with OSR SHA-256 values. Account for Git clean filters/line-ending normalization with a documented, tested rule; unsupported transformation fails with a diagnostic, never silent acceptance. A local hook remains bypassable with --no-verify; document that limitation.
8. Persist new state through existing tool-managed writes and locks. Do not manually edit state or ledger. Do not claim atomic multi-file transactions merely because ledger append uses a lock. Tests exercise interrupted/missing records and require rejection.

## Execution order
Historical technical sequence completed: T22 logs -> T23 authorization -> T24 test identity -> T25 freshness. Their cards are retired into .ai/archive/pre-baseline-transition/; ledger/state history and snapshots remain intact. T25 closed explicitly as UNVERIFIED legacy technical history.

Active sequence after human reapproval: T26 commit gate -> T27 integration/documentation. T26 starts from the newly approved baseline; T27 retains every requirement R20-R25 and must provide fresh current-epoch evidence. No retired task supplies current requirement credit. One builder and task at a time, with independent supervisor review before closure or advance. See .ai/TRANSITION.md.

## Assumptions
- [x] Existing working-tree modifications are user work; activation requires an explicit ownership inventory and baseline, not a reset or stash.
- [x] The active cards are T26 and T27. Original roadmap artifacts remain in .ai/archive/deferred/; pre-transition plan/cards are preserved in .ai/archive/pre-baseline-transition/. No ledger/state history was manually edited. Human reapproval is required before implementation resumes.
- [x] Security corrections intentionally reject some previously accepted commands/evidence; compatibility does not mean preserving these bypasses.
- [x] Local tests run sequentially in scoped batches, consistent with the parent AGENTS.md. No monolithic full-suite command is authorized by this packet.

## Open questions
Pending human approval of this reviewed transition and the new starting baseline. No agent may execute approve-plan. No additional scope or acceptance-criterion change is proposed.
