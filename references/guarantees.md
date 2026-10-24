# What this skill guarantees, and what it does not

Be honest with the human about this. Overclaiming is the fastest way to lose their trust.

## Contents
- The promise
- What is mechanical
- Approval freshness and legacy migration
- Staged-content checks
- Recorded validation
- What is not
- Residual risks and how to reduce them

## The promise

**No silent failure.** Nothing is accepted without machine-produced evidence. Anything that cannot be machine-checked is labelled UNVERIFIED and routed to a human. A failure is caught or surfaced, not hidden behind a confident summary.

It is **not** a promise of 100% correct code. No process can promise that, because the plan itself can be wrong and some qualities have no automatic check.

## What is mechanical

| AI limitation | Mechanical defense | Remaining gap |
|---|---|---|
| Fake "tests pass" claims | `osr verify` runs the commands and writes the evidence itself | none for the recorded run; the test itself can still be weak |
| Unapproved command variants | exact-string matching against ledger-confirmed commands; `verified: true` alone is insufficient | a human confirming a genuinely bad command |
| "Exit 0 but nothing ran" | suspect-output detection marks a recognised zero-test run as failure | custom runners with unrecognisable output |
| Skipped workflow steps | each command refuses unless prior gates passed | the human bypassing the tool |
| Scope drift | snapshot diff against `allowed_files` | wrong edits inside allowed files |
| Elided or truncated code | placeholder and shrinkage flags | subtle omissions |
| Weakened tests | assertion-count and skip-marker flags, human-approved waiver | rewrites that keep the count (see tautology heuristics) |
| Hallucinated imports | Python and JS/TS resolution; syntax checks | other languages need a compiler command |
| Fabricated review evidence | cited file, line and snippet are checked against the real file | evidence that is real but irrelevant |
| Lazy reviews | strict format, per-check notes, break attempts, no re-submitting an old review | shallow but well-formatted reviews |
| Blind retry loops | failure cap, mandatory triage, input-change rules | misdiagnosis of the layer |
| Stale approvals | approval baseline, start/accepted-map equality, replayed completion deltas, work fingerprints | a human approving the wrong bytes |
| Tampered records | hash-chained ledger and external anchoring (`osr anchor`) | an external anchor covers only the ledger prefix it pinned, and only while a trusted verifier actually compares it; it does not establish the truth of later entries, test quality, actor identity, or the correctness of mutable state and tooling |
| Unstaged or stale commit content | pre-commit runs `audit --check`, then compares the complete governed index with the audited working tree | repository hooks not installed |
| Context bloat | card length cap, context budget, state in files | the budget being set too high |
| Uncovered requirements | coverage check and final audit | requirement wrongly written |

### Approval freshness and legacy migration

`approve-plan` binds a baseline manifest of governed paths and SHA-256 digests. `start` refuses to begin when the tree differs from the last accepted map, and `done` records a completion delta that later audits replay in order. This preserves historical task credit without adopting unreviewed bytes. Any later edit to `PLAN.md`, `config.json` or the configured ignore policy requires a human re-approval and a new start.

Approval epochs recorded before baselines existed are **legacy**. Their closures can still be traced (start, verify and review references) but they earn no current requirement credit; the audit reports them UNVERIFIED. The tool never fabricates a baseline for them, and it never silently rebases active work onto a new approval.

### Staged-content checks

The git pre-commit helper is read-only. It asks the CLI for `audit --check`, then uses Git plumbing to compare every proposed index entry with the audited working tree. This covers the complete **governed** index required by the current governance and the configured ignore policy, not every file that happens to exist in the workspace. Equal bytes pass for a supported regular-file entry, including `-text`/`binary` paths. This is not an unconditional byte-equality guarantee: a difference confined to CRLF/LF is accepted only when Git's effective attributes say the path is stored as text, while differing `-text`/`binary` bytes are rejected without newline normalization. Unsupported clean filters, `working-tree-encoding`, `ident`, merge stages and non-regular modes are rejected with a diagnostic even when their bytes happen to be equal. Passing this hook is local evidence for one checkout; it is not proof that another platform or checkout stores the same bytes.

## Recorded validation

For commit `58a16e6`, the configured Ubuntu/macOS/Windows × Python 3.8–3.12 matrix completed successfully in both the [15-job push run](https://github.com/De-pitcher/orchestrator-supervisor-reviewer/actions/runs/40043049298) and [15-job PR run](https://github.com/De-pitcher/orchestrator-supervisor-reviewer/actions/runs/40043053441), with no skipped matrix jobs. Current discovery is 251 tests. The original 249-test integration record predates the two CI portability regressions and remains historical evidence.

These runs execute tests, ledger verification and plan validation. They are not a final audit of every downstream project, proof that an external harness enforces hooks, or proof of identical raw approval baselines across checkouts. Local Windows/Python 3.14.3 checks are separate; Python 3.13 is not covered by these recorded runs. Successful tests do not remove the limitations below.

## What is not

- **Plan correctness.** If the human approves a wrong plan, the tool builds the wrong thing perfectly.
- **Test quality.** "All green" means the checks passed, not that the checks are good. Weak acceptance criteria give weak tests.
- **Semantic test strength.** Tautology detection is AST/regex heuristics for common patterns; it is not mutation testing and cannot prove a test would fail on a real defect.
- **Every possible runner.** Zero-test detection parses recognised output from common runners. A custom runner with unusual output may need an explicit count threshold or a pluggable checker.
- **Every verbose unittest shape.** Named-evidence extraction accepts the supported one-line shape (`test_x (mod.Class.test_x) ... ok`). Standard unittest method docstrings put the identity and the `... ok` status on separate lines; the current parser then omits the test from `canonical_tests`. A declared negative test in that shape is rejected even though it actually ran and passed. That is conservative missing evidence, not false acceptance; extending multiline parsing belongs to a separate scoped parser change. Do not assume every executed test ID is represented in `canonical_tests`, or that every verbose unittest format is supported.
- **Full end-to-end benchmark coverage.** The clean canaries reach `osr check`; they do not exercise a complete `start → verify → review → done` flow and do not prove semantic correctness.
- **Subjective quality.** Design, UX, copy, naming taste, product fit. These are UNVERIFIED until a human signs off.
- **Languages without a checker.** Reference checking is built in for Python and JS/TS; any other language can plug in external checkers via `.ai/config.json`.
- **Who runs what.** `--by` is a self-reported label, not authenticated identity. `OSR_APPROVAL_SECRET` is optional and, when configured, only proves possession of the configured secret. The Antigravity hooks in `integrations/` intercept the tool-call shapes configured in that harness; they are not an OS permission boundary and do not stop a builder that invokes the CLI directly. A builder-executed `osr reset --by <human name>` is accepted exactly like any other label. Authenticating the actor is part of the deferred password/harness redesign; the current workflow does not implement it.
- **Anchored truth.** An external anchor protects the committed ledger prefix against rewriting or rollback only when a trusted verifier compares it out of band. It does not make later (suffix) entries true, does not prove test quality, does not identify the human actor, and does not vouch for mutable state or tooling the builder can rewrite.
- **Security.** It flags secrets and review check C3 prompts for security thinking, but it is not a full vulnerability scanner. Run dedicated tools.

## Residual risks and how to reduce them

1. **Weak acceptance criteria.** Have the human review ACs, or write tests first and have the human approve them.
2. **Tests written by the same model as the code.** Have a different model write or review tests.
3. **Mutation or property-based testing** where the stack supports it, as a global command. Raises the bar against tests that cannot fail.
4. **Add a compiler, type-checker, linter and security scanner** as confirmed global commands. Each is another mechanical gate.
5. **Run the human-only steps for real.** The ledger shows who approved the plan and who signed off what. Exact-command confirmation proves *which* command ran, not that the command is a strong test.
6. **Keep an out-of-band anchor and verify it independently.** An `.osr-anchor` stored inside the repository can be rewritten by the same actor that rewrites the ledger. Store it where the builder has no write access and have a trusted verifier compare it. The anchor only covers the prefix it pinned; entries appended afterwards and the correctness of new evidence still need review.
