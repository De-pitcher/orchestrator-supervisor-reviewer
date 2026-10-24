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

The shipped `.github/workflows/test.yml` checks full test discovery, ledger integrity and plan syntax on Ubuntu/macOS/Windows with Python 3.8–3.12. It does not run a final acceptance audit or compare a trusted external anchor. For a project's acceptance gate, configure those separately. For example, on a Linux CI runner with a supervisor-controlled anchor mounted read-only:

```yaml
- run: python path/to/scripts/osr.py ledger-verify --anchor /mnt/supervisor/osr-anchor
- run: python path/to/scripts/osr.py audit --check --anchor /mnt/supervisor/osr-anchor
```

`ledger-verify` checks the hash chain; detecting rollback requires comparison with a trusted anchor outside the builder's write access. `osr anchor --out <external-path>` writes a pin for the current ledger sequence and hash. A pin protects that prefix only while independently compared: it does not validate later entries, actor identity, tests or mutable tooling. `audit --check` evaluates accepted content without writing project files or rerunning verification commands. Audit exits nonzero for failures or UNVERIFIED evidence, including legacy epochs without baseline metadata; code 2 can also indicate pending human sign-off. Do not treat every nonzero result as a request for sign-off.

## Harness enforcement & Antigravity hooks

These controls apply within configured execution paths; they are not an OS permission boundary:
- **Antigravity Hooks (`integrations/antigravity/hooks.json`)**: `pre_tool.py` checks the tool-call shapes it recognizes, denying writes outside the active card and the listed commands (`approve-plan`, `unblock`, `signoff`, `reset`). Direct CLI execution outside that harness bypasses these interceptions; `waive` is not in that command list.
- **Completion Gate (`stop_hook.py`)**: Inspects task state and, when it considers the workflow incomplete, returns continuation instructions with the next action. It does not provide an independent acceptance audit or guarantee the harness enforces its response.
- **Git Pre-Commit Hook (`integrations/git/pre_commit.py`)**: If installed and invoked, requires read-only `audit --check` and compares the complete governed index with the audited working artifact, including required governance evidence. It never stages or reruns tests. Install the executable wrapper using [the integration guide](../integrations/README.md); `--no-verify` bypasses it.
- **Approval Secrets (`OSR_APPROVAL_SECRET`)**: Optional configured secrets require possession of the secret for protected commands; `--by`, model and reviewer names remain self-reported labels. Keep actual secrets outside the repository. This is not human-actor authentication.

## Team habits

- Commit `.ai/PLAN.md`, current `tasks/` and `reviews/`, `ledger.jsonl`, `config.json` and `state.json`. Retain selected raw logs when needed for reproducible evidence, preserving their hashed bytes. Logs and snapshot caches are normally ignored; baseline-backed replay can work without the cache, but conflicting caches are rejected.
- Store the trusted anchor outside the builder's write access. An in-repository `.osr-anchor` may be a convenience copy, but is not independent rollback protection.
- Confirm exact command strings before approval; a different argument, quote or internal whitespace needs its own confirmation. Changed plan/configuration requires fresh human approval, and only one task may be active. Legacy completion history without current baseline bindings does not earn current requirement credit.
- On a team repository, treat `PLAN.md` approval like merging a design doc.
