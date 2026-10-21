# What this skill guarantees, and what it does not

Be honest with the human about this. Overclaiming is the fastest way to lose their trust.

## Contents
- The promise
- What is mechanical
- What is not
- Residual risks and how to reduce them

## The promise

**No silent failure.** Nothing is accepted without machine-produced evidence. Anything that cannot be machine-checked is labelled UNVERIFIED and routed to a human. A failure is caught or surfaced, not hidden behind a confident summary.

It is **not** a promise of 100% correct code. No process can promise that, because the plan itself can be wrong and some qualities have no automatic check.

## What is mechanical

| AI limitation | Mechanical defense | Remaining gap |
|---|---|---|
| Fake "tests pass" claims | `osr verify` runs the commands and writes the evidence itself | none for the claim |
| "Exit 0 but nothing ran" | suspect-output detection counts it as failure | unusual test runners |
| Skipped workflow steps | each command refuses unless prior gates passed | the human bypassing the tool |
| Scope drift | snapshot diff against `allowed_files` | wrong edits inside allowed files |
| Elided or truncated code | placeholder and shrinkage flags | subtle omissions |
| Weakened tests | assertion-count and skip-marker flags, human-approved waiver | rewrites that keep the count |
| Hallucinated imports | Python and JS/TS resolution; syntax checks | other languages need a compiler command |
| Fabricated review evidence | cited file, line and snippet are checked against the real file | evidence that is real but irrelevant |
| Lazy reviews | strict format, per-check notes, break attempts, no re-submitting an old review | shallow but well-formatted reviews |
| Blind retry loops | failure cap, mandatory triage, input-change rules | misdiagnosis of the layer |
| Stale approvals | work fingerprints; any change after verify or review invalidates them | none |
| Tampered records | hash-chained ledger and external anchoring (`osr anchor`) | none when anchored externally |
| Context bloat | card length cap, context budget, state in files | the budget being set too high |
| Uncovered requirements | coverage check and final audit | requirement wrongly written |

## What is not

- **Plan correctness.** If the human approves a wrong plan, the tool builds the wrong thing perfectly.
- **Test quality.** "All green" means the checks passed, not that the checks are good. Weak acceptance criteria give weak tests.
- **Subjective quality.** Design, UX, copy, naming taste, product fit. These are UNVERIFIED until a human signs off.
- **Languages without a checker.** Reference checking is built in for Python and JS/TS; any other language can plug in external checkers via `.ai/config.json`.
- **Who runs what.** Cryptographic secrets (`OSR_APPROVAL_SECRET`) and Antigravity workspace deny hooks enforce human authority.
- **Security.** It flags secrets and review check C3 prompts for security thinking, but it is not a full vulnerability scanner. Run dedicated tools.

## Residual risks and how to reduce them

1. **Weak acceptance criteria.** Have the human review ACs, or write tests first and have the human approve them.
2. **Tests written by the same model as the code.** Have a different model write or review tests.
3. **Mutation or property-based testing** where the stack supports it, as a global command. Raises the bar against tests that cannot fail.
4. **Add a compiler, type-checker, linter and security scanner** as confirmed global commands. Each is another mechanical gate.
5. **Run the human-only steps for real.** The ledger shows who approved the plan and who signed off what.
