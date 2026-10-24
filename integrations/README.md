# Integrations

This directory provides out-of-the-box integration hooks for development environments, agent harnesses, and version control.

## Antigravity Workspace Integration (`integrations/antigravity/`)

Enforces the gates below for the tool-call shapes configured in the Antigravity harness. It is **not an OS permission boundary**: a process that invokes `scripts/osr.py` directly bypasses these hooks. `--by` is a self-reported label and `OSR_APPROVAL_SECRET` is optional, so neither the hooks nor the label authenticate the human actor.

- **`hooks.json`**: Configures workspace-level hooks for `PreToolUse` and `Stop` events.
- **`pre_tool.py`**:
  - Intercepts file modification tools (`write_file`, `edit_file`) and blocks any edit outside the active task's `allowed_files` boundary with an immediate `deny` decision.
  - Intercepts command execution tools (`run_command`) to hard-block agent execution of the human-only commands it recognises: `approve-plan`, `unblock`, `signoff`, `reset`.
  - Blocks attempts to read the approval secret.
- **`stop_hook.py`**:
  - Intercepts `Stop` events when the agent attempts to conclude its work.
  - Runs `osr next`; if unfinished tasks remain, it forces continuation (`terminationBehavior: force_continue`) with actionable instructions.

### Installation in Antigravity
Copy or symlink `integrations/antigravity/hooks.json` into your workspace `.agents/` directory or global configuration `~/.gemini/config/`.

---

## Git Pre-Commit Hook (`integrations/git/`)

Checks the governed staged artifact when Git invokes this hook. The hook is deliberately read-only: it never stages, repairs, refreshes or rewrites anything, and it never runs a configured test command.

- **`pre_commit.py`**:
  - Runs `osr audit --check` against the current working artifact and refuses the commit unless it exits `0`. This includes the hash-chained ledger check, approval freshness and the requirement/evidence audit.
  - Compares the **complete governed** proposed index with the audited working tree using NUL-safe Git plumbing (`ls-files --stage`, `cat-file --batch`, `check-attr`). The guarantee covers the governed artifact under the current governance and configured ignore policy, not every workspace file.
  - Equal bytes pass for a supported regular-file entry, including `-text`/`binary` paths. A difference confined to CRLF/LF is accepted only when Git's effective attributes treat the path as text. Differing `-text`/`binary` bytes are rejected without newline normalization. Unsupported clean filters, `working-tree-encoding`, `ident`, merge stages and non-regular modes are rejected with a diagnostic even when the bytes happen to be equal.
  - Fails closed when the OSR tooling is unavailable or the governance artifact is missing.
- **`pre-commit`**: Shell entry point invoking `python pre_commit.py`.

> **Trust boundary:** the hook's parity check is local evidence for one checkout. It does not verify an out-of-band `.osr-anchor`, and it cannot prove that another platform or checkout reproduces the same bytes. Use `osr ledger-verify --anchor <external-path>` and `osr audit --anchor <external-path>` for rollback evidence kept outside the builder's write access. An external anchor protects the ledger prefix it pinned only while a trusted verifier compares it; it does not establish the truth of later entries, test quality, actor identity, or the correctness of mutable state and tooling.

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
