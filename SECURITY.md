# Security policy

## Report privately

Use [GitHub's private vulnerability reporting form](https://github.com/De-pitcher/orchestrator-supervisor-reviewer/security/advisories/new).
Private vulnerability reporting is enabled for this repository. Do not disclose
an unpatched exploit, credentials, private project data or complete sensitive
ledgers in a public issue.

Include the affected commit/tag, Python and OS versions, the exact commands,
expected and observed behavior, and a minimal reproduction. Redact secrets and
private paths. Maintainers will assess the report and coordinate fixes and any
disclosure on a best-effort basis; no response or remediation SLA is promised.

## Supported development state

The development branch and current `main` are the initial investigation targets.
Older commits are not promised security backports. Package metadata currently
says 0.3.1; that number does not establish a published or maintained release.
There are no GitHub releases at the time this policy is introduced. Consult
[release guidance](docs/RELEASING.md) and the [changelog](CHANGELOG.md) for actual
publication history and future support decisions.

## Trust boundaries

OSR is workflow enforcement, not an isolation sandbox. In particular:

- A writer who controls the tool, ledger and state can rewrite the evidence.
- `--by` and reviewer/model labels are not authenticated identities. The
  approval secret is optional and establishes possession, not human identity.
- Local Git hooks can be bypassed with `--no-verify`; harness hooks only see
  configured tool-call paths. `allow_no_commands` is an explicit escape.
- External anchors cover their pinned prefix only while independently compared.
- Static heuristics and a passing test suite do not prove semantic correctness.

These disclosed limitations do not make further bypass research unwelcome.
Report behavior that violates a claimed boundary privately with a reproduction.
See [guarantees and remaining gaps](references/guarantees.md) for the precise
current claims. Do not test against other people's repositories or data.
