# Setups and tools

The skill is stack-agnostic and tool-agnostic. All it needs is a way to read and write project files and, ideally, run a shell command. The enforcement script needs Python 3.8 or newer on the machine running it; the project itself can be any language.

## Contents
- One agent, one session
- Several agents or models
- Chat only, no shell
- Using it inside different tools
- Continuous integration
- Team habits (git, human steps)

## One agent, one session

Works, with weaker assurance. Rules that keep it honest:
- Run `osr next` before every action.
- Reviewer hat: reread changed files from disk, write the review fresh, do not reuse wording from your own plan.
- The audit will list tasks as self-reviewed. That is the truth; do not hide it.
- Start a new session at each task boundary when the tool allows it. State lives in `.ai/`, so nothing is lost.

## Several agents or models

Best assurance. Suggested split:
- **Orchestrator**: strongest model available. Owns PLAN.md, cards and triage.
- **Builder**: any model. One task per session.
- **Reviewer**: a different model than the builder. Writes the review files and runs `review`.

Pass `--model` on `osr start` and `--reviewer` on `osr review` so the ledger records who did what. Agents share state only through `.ai/` files, which is why they can run in separate sessions or tools.

## Chat only, no shell

Use `PROMPT-ONLY.md`. The human runs commands and pastes output; the AI applies the same gates by hand. This is weaker (the human becomes the enforcement mechanism) but keeps the structure and the evidence discipline.

## Using it inside different tools

Any agentic coding tool or IDE agent that can read files and run a shell works. Install the folder wherever that tool loads skills or instructions from, or point its project instructions at `SKILL.md`. Where the tool does not support skill folders, paste the Iron rules and workflow sections of `SKILL.md` into its rules or system-prompt file, and keep `scripts/`, `assets/` and `references/` in the repository so the paths resolve. Check each tool's own documentation for where instructions live; they differ and change.

Set an alias or wrapper so `osr` is short:
- macOS/Linux: `alias osr='python3 /path/to/orchestrator-supervisor-reviewer/scripts/osr.py'`
- Windows PowerShell: `function osr { python C:\path\to\orchestrator-supervisor-reviewer\scripts\osr.py @args }`

The project root is the current directory, or pass `--root <path>` before the command.

## Continuous integration & Anchoring

The ledger, plan, and anchor make solid CI gates. A minimal job:

```yaml
- run: python path/to/scripts/osr.py ledger-verify --anchor .osr-anchor
- run: python path/to/scripts/osr.py audit
```

`ledger-verify` fails if the ledger was edited, rolled back, or truncated. `osr anchor` commits the current ledger sequence and hash externally to prevent rollback attacks. `audit` fails (exit 1) if requirements are uncovered or tasks are unfinished, and exits 2 when only human sign-offs are pending; decide in CI whether 2 should block.

## Harness enforcement & Antigravity hooks

To prevent agents from bypassing human authority or widening scope:
- **Antigravity Hooks (`integrations/antigravity/hooks.json`)**: Configures `PreToolUse` hooks (`pre_tool.py`) that read active task cards and hard-deny any file modifications outside `allowed_files`. Also intercepts and denies attempts by the agent to run human-only commands (`approve-plan`, `unblock`, `signoff`, `reset`) or read approval secret files.
- **Completion Gate (`stop_hook.py`)**: Checks `osr next` before allowing an agent session to terminate, preventing premature completion when tasks remain undone.
- **Git Pre-Commit Hook (`integrations/git/pre_commit.py`)**: Validates ledger integrity and ensures all active changes comply with plan approval before any `git commit` succeeds.
- **Approval Secrets (`OSR_APPROVAL_SECRET`)**: Configure an environment secret or external token file. Human commands require `--secret <token>`, preventing unauthorized self-approval.

## Team habits

- Commit `.ai/PLAN.md`, `tasks/`, `reviews/`, `ledger.jsonl`, `config.json`, `state.json`, and `.osr-anchor`. `.ai/.gitignore` already excludes logs and snapshots.
- On a team repository, treat `PLAN.md` approval like merging a design doc.
