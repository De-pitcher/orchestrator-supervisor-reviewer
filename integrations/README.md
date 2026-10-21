# Integrations

This directory provides out-of-the-box integration hooks for development environments, agent harnesses, and version control.

## Antigravity Workspace Integration (`integrations/antigravity/`)

Enforces supervisory gates directly within the Antigravity agent execution harness.

- **`hooks.json`**: Configures workspace-level hooks for `PreToolUse` and `Stop` events.
- **`pre_tool.py`**:
  - Intercepts file modification tools (`write_file`, `edit_file`) and blocks any edit outside the active task's `allowed_files` boundary with an immediate `deny` decision.
  - Intercepts command execution tools (`run_command`) to hard-block agent execution of human-only commands (`approve-plan`, `unblock`, `signoff`, `reset`, `waive`).
  - Blocks agent inspection of approval secrets.
- **`stop_hook.py`**:
  - Intercepts `Stop` events when the agent attempts to conclude its work.
  - Runs `osr next`; if unfinished tasks remain, it forces continuation (`terminationBehavior: force_continue`) with actionable instructions.

### Installation in Antigravity
Copy or symlink `integrations/antigravity/hooks.json` into your workspace `.agents/` directory or global configuration `~/.gemini/config/`.

---

## Git Pre-Commit Hook (`integrations/git/`)

Guarantees repository integrity before any commit can be created.

- **`pre_commit.py`**:
  - Runs `osr ledger-verify` against the append-only ledger and `.osr-anchor` to detect history tampering or rollback.
  - Verifies that `PLAN.md` has not been tampered with or edited without human re-approval.
- **`pre-commit`**: Shell entry point invoking `python pre_commit.py`.

### Installation in Git
Copy `integrations/git/pre-commit` into `.git/hooks/pre-commit` and ensure executable permissions:
```bash
cp integrations/git/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```
On Windows PowerShell:
```powershell
Copy-Item integrations/git/pre-commit .git/hooks/pre-commit
```
