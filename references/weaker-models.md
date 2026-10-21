# Working with smaller or less reliable models

This applies if you are a smaller model, or if you are supervising one (DeepSeek, Gemini, local models, anything that is not at the frontier). The skill was designed so that weaker models can succeed: the script does the judging, and your job shrinks to doing small clear steps and obeying the gates. You do not need to be brilliant. You need to be literal.

## Contents
- Operating rules
- Known failure habits and countermeasures
- Supervising a weaker model
- Prompt and format tips

## Operating rules

1. **Run `osr next` and do exactly what it says.** Do not plan ahead beyond it.
2. **Do one thing at a time.** One task, one file at a time within the task. Do not batch.
3. **Copy, do not recall.** When citing code, copy from the file you just opened. When using a name, copy it from where it is defined.
4. **When blocked, stop and say so.** "I cannot find X" is a correct and valuable output. A guess is not.
5. **Write the full file or use a targeted edit.** Never output "rest of file unchanged".
6. **After every edit, rerun `osr verify`.** Do not predict the result.
7. **Short outputs.** Report what the tool printed, the next action, and any blocker. Skip essays.

## Known failure habits and countermeasures

| Habit | What it looks like | Countermeasure in this skill |
|---|---|---|
| Hallucinated references | imports or calls to things that do not exist | `check` resolves Python and JS/TS imports; rule 4; reviewer check C1 |
| Fake success | "all tests pass" with no run | evidence only from `osr verify`; the tool captures output itself |
| Elision | "..." or "rest unchanged" in a rewritten file | placeholder and shrinkage flags; rule 3 |
| Test gaming | deleting assertions, adding skips, mocking the subject | tests-weakened and skips-added flags need human-approved waiver |
| Scope creep | refactoring neighbours, renaming, adding deps | allowed_files lock, C8 |
| Instruction decay | follows the first rules, forgets later ones in long sessions | `osr next` re-derives the step from files; fresh session per task |
| Premature "done" | declares finished early | `osr done` refuses without gates |
| Confident misdiagnosis | explains a failure wrongly and loops | triage questions need evidence; layer enforces a changed input |
| Over-long context | quality collapses as the session grows | context budget; state lives in `.ai/`, not in chat |
| Lazy review | "looks good" | review format demands cited evidence and break attempts |

## Supervising a weaker model

- **Give it smaller tasks than you think it needs.** If a card fails on a weak model and passes on a strong one, split the card instead of retrying.
- **Use a stronger model (or a different one) as reviewer** when you can. Diversity catches blind spots.
- **Put a worked example in every card.** Examples steer weaker models more than abstract rules.
- **Keep the plan and cards in plain direct language.** Avoid idioms, nested conditionals, and long paragraphs. One instruction per sentence.
- **Start a fresh session per task** and let `.ai/` carry the state. Long sessions degrade weaker models quickly.
- **Check the ledger, not the chat.** `osr status`, `osr coverage`, `osr audit`. Treat the model's own summary as a claim to verify.
- **Run `osr ledger-verify` in CI** so skipped or edited records fail the build.

## Prompt and format tips

- Use plain Markdown and plain ASCII where you can. The review formats are strict line formats (`R1: PASS @ file:line "snippet"`); copy them from `assets/`.
- If a model keeps wrapping output in code fences or adding bullets inside review files, that is fine: the parser strips leading bullets and bold markers. It does not strip anything else, so keep each requirement on its own line.
- If a model cannot run a shell, use `PROMPT-ONLY.md` and have a human paste command output in.
- If a model ignores this skill file entirely, paste the "Iron rules" and the "workflow" sections into its system or project instructions. The scripts enforce the rest.
