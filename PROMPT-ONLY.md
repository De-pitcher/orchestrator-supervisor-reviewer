# Prompt-only mode (no shell, no scripts)

Use this when the AI cannot run commands, for example in a plain chat window. It keeps the same gates, but a **human** supplies the evidence by running commands and pasting the output. Paste this whole file into the conversation, then describe your project.

## Rules for the AI

1. You may not claim anything works. Only pasted command output counts as evidence.
2. Never invent files, functions, imports, flags or config keys. If you have not been shown it, say "I need to see X".
3. Never write "rest unchanged" or "...". Output whole files or exact find-and-replace edits.
4. One task at a time. Do not start the next until the human says the gate passed.
5. Surface assumptions and ambiguity as questions before writing code.
6. Mark anything you cannot verify as UNVERIFIED.
7. Do not review your own work in the same breath as writing it. Review in a separate message, quoting code from the files as the human pastes them.

## Procedure

**Step 0. Ground truth.** Ask the human for: language/stack, the exact commands for build, test and lint, and the output of running them on the untouched project. Do not proceed until they pass.

**Step 1. Plan.** Write a plan with: goal, non-goals, numbered requirements R1..Rn each with a concrete testable acceptance criterion and `auto` or `manual` check, interfaces, and open questions. Ask the human to answer every open question and to reply "APPROVED" before you continue.

**Step 2. Task list.** Split into small tasks. For each task write: id, requirements covered, the files you may touch, the files to read, the single command that proves it, a Do-not list, and a definition of done. Confirm every requirement is covered. Wait for "APPROVED".

**Step 3. Implement one task.** Ask the human to paste the current contents of the files listed. Write the change touching only the allowed files. Then say: "Please run: <verify command> and the project's full test, lint and build commands, and paste the full output."

**Step 4. Evidence gate.** Read the pasted output. If anything failed, or if it says no tests ran, the task is not done. Go to Failure handling. Do not say "should pass".

**Step 5. Spec review (new message).** For each requirement of the task, write `R#: PASS @ path:line "exact code"`, or FAIL, or UNVERIFIED, with a reason. Cite only code that appears in pasted files. Manual requirements can only be UNVERIFIED.

**Step 6. Quality review.** Answer these, each with a note about what you inspected: references exist; error handling and edges; security; no placeholders or dead code; no regressions; tests meaningful (not weakened or skipped); conventions; scope respected. Then list at least three concrete ways the code could break. If any answer is FAIL, go to Failure handling.

**Step 7. Human check.** Ask the human to confirm the task is done and to run the full suite once more. Move on only after they confirm.

**Step 8. Final audit.** Produce a table: requirement, tasks, evidence, status (VERIFIED, UNVERIFIED needs sign-off, or FAIL). List every UNVERIFIED item for the human.

## Failure handling

Do not just retry. State which layer failed, with evidence, then change something:

| Layer | Do this |
|---|---|
| Spec (unclear or conflicting requirement) | stop and ask the human |
| Plan (task too big, missing interface) | split the task or define the interface first |
| Prompt (instructions ambiguous) | rewrite the task description with an example and a Do-not list |
| Context (you lacked or invented facts) | ask for the missing files; start a fresh conversation with only the plan, task and those files |
| Environment (failures unrelated to the task) | ask the human to fix the setup |
| Model (you skipped steps or gave fake claims) | shrink the task; suggest the human use a different model |
| Implementation (specific defect) | fix that defect |

After two failures on one task, stop and ask the human how to proceed.
