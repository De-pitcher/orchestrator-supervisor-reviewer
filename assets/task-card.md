# T1: <short title>
<!-- A task card is a SELF-CONTAINED PROMPT. A fresh agent with no chat history must be able to do the task from this file
     plus the listed context files alone. Keep it under 150 lines. Keys below are parsed by tooling: one per line, exact names. -->
id: T1
requirements: R1
depends_on:
allowed_files: src/feature/**, tests/test_feature.py
forbidden_files:
context_files: src/feature/api.py
verify: python -m pytest tests/test_feature.py -q

## Goal
<What to build or change, and WHY it matters. One goal only.>

## Inputs and context
<Exact facts the agent needs: file roles, existing function names, data shapes. Do not make it infer these.>

## Constraints
- <Language/framework/version, style rules, performance or compatibility limits.>

## Do not
- Do not touch files outside allowed_files.
- Do not add dependencies unless this card says so.
- Do not weaken, skip, or delete existing tests.
- <Anything plausible but wrong for this task.>

## Example
<One small example of correct input and output, or a snippet showing the expected style.>

## Definition of done
- <Observable outcome 1, matches the AC of the listed requirements.>
- The verify command(s) above pass for real.
