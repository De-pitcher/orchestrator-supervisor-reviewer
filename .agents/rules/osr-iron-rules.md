# OSR Iron Rules & Self-Enforcement Directives

These rules apply when developing and modifying the `orchestrator-supervisor-reviewer` repository. Every agent must strictly abide by them.

## The Prime Rule
> **The AI proposes. The tool decides. Nothing the AI says counts as evidence.**

Evidence is strictly command output captured by `osr`, file hashes, snapshot diffs, and machine-verified reviews.

## The Ten Iron Rules
1. **No claim without tool evidence**: "Done", "works", "tests pass" are only true when `osr` verifies and logs them. A model's summary of a test run is not a test run.
2. **Read before you write**: Open and inspect every file before modifying it, including the active task card's `context_files`. Never guess file contents or APIs.
3. **Never elide**: Never write "rest unchanged", `...`, or placeholder stubs. Full, syntactically complete code only.
4. **Never invent references**: Verify imports, functions, flags, and configuration keys exist before using them.
5. **Stay inside the card**: Modify only `allowed_files` specified in the active task card. Expanding scope without an explicit card update is strictly forbidden.
6. **Never weaken a test to make it pass**: Never delete assertions, add skip markers, or loosen thresholds to turn tests green. Fix the underlying implementation or request human guidance.
7. **Surface assumptions early**: Unverified assumptions must be surfaced to the human operator before implementation.
8. **Every retry must change something**: Identical inputs yield identical failures. Diagnose failure layers (spec, plan, prompt, context, environment, model, implementation) before retrying.
9. **Mark unverified aspects as UNVERIFIED**: Visual polish, subjective UX, and design aesthetics cannot be mechanically proven and must be marked for human review.
10. **Humans own supervisory commands**: Only the human operator may execute `approve-plan`, `unblock`, `signoff`, `reset`, or waivers on tests, skips, or secrets. Never execute these as an AI agent. Always stop and prompt the human.
