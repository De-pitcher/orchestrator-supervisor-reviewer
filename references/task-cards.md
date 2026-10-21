# Writing task cards

A task card is a **self-contained prompt**. A fresh agent with no chat history, a weaker model, or a different tool must be able to do the work from the card and its listed context files alone. If your card relies on "as we discussed", it is broken.

## Contents
- Decomposition rules
- Anatomy of a good card
- Choosing `allowed_files`
- The context packet
- Choosing a `verify:` command
- Common card mistakes

## Decomposition rules

- **One goal per card.** If the goal needs "and", split it.
- **Fits in one session.** The builder should be able to read the card plus context, implement, and verify without running out of room. The tool enforces a card length cap and a context budget; hitting them means split.
- **Interfaces first.** If two tasks must agree on a function signature, schema or file format, write it into the plan's Interfaces section first and give both cards that section.
- **Order by dependency.** Use `depends_on:`. Foundations (scaffolding, test harness, shared types) come first.
- **Test-first when possible.** For logic that can be tested, make the first task write failing tests from the acceptance criteria and have the human approve them. A different model writing the tests than the one implementing is stronger still.
- **Add an integration task** after tasks that depend on each other.
- **Every requirement maps to at least one task.** `osr task-check --all` rejects uncovered requirements.

## Anatomy of a good card

Use `assets/task-card.md`. The parsed keys are `id`, `requirements`, `depends_on`, `allowed_files`, `forbidden_files`, `context_files`, `verify`, one per line. The sections `Goal`, `Constraints`, `Do not`, `Definition of done` are required. Strongly recommended: `Inputs and context` and `Example`.

- **Goal** says what and why, in two or three sentences.
- **Inputs and context** states facts the builder would otherwise guess: names of existing functions, data shapes, where things live.
- **Constraints** are the rules of this task: versions, style, limits.
- **Do not** lists plausible-but-wrong moves. This is where you prevent the specific mistake you can already foresee (adding a dependency, rewriting a neighbouring module, mocking the thing under test).
- **Example** shows one input and expected output, or a snippet in the house style. Examples steer weaker models more reliably than adjectives.
- **Definition of done** restates the acceptance criteria as observable outcomes.

Write imperatively and explain why for non-obvious constraints. "Use the existing `db.session()`; opening a new connection breaks transaction handling" gets followed. "Use the existing session" gets ignored.

## Choosing `allowed_files`

List the specific files or folders the task should change, plus its tests. The tool rejects `**` and `*` alone. If the builder needs a file outside the list, the card is wrong; that is a triage event, not a license to widen scope.

Globs: `*` matches within a folder, `**` crosses folders, a trailing `/` means the whole folder. Separate entries with commas.

## The context packet

`context_files` is the complete set of existing files the builder reads. Include the files it must call, extend or imitate, and any contract it must obey. Exclude everything else. Smaller is better: models perform worse as context grows, and unrelated files invite unrelated edits. Do not paste whole modules "just in case".

## Choosing a `verify:` command

It must test **this task**, so a failure means this task is wrong and a pass means it is plausibly right. Prefer the narrowest real test command (a single test file or pattern). Global commands (full test suite, lint, build) are configured once in `.ai/config.json` and run automatically on every `verify`, so do not repeat them in cards.

The tool rejects commands that cannot prove anything (`echo`, `true`) and treats "exit 0 but no tests ran" as failure. If a requirement has no automatic check, mark it `Check: manual` in the plan; do not invent a fake command.

## Common card mistakes

- Goal is a theme ("improve error handling"), not an outcome.
- Verify command runs the whole suite and passes before any work is done.
- Context lists a dozen files; the builder skims and guesses.
- No Do-not list, so the builder "helpfully" refactors the neighbour.
- Acceptance criteria say "works correctly" with no input and expected output.
