# Getting help

Start with [README.md](README.md), [SKILL.md](SKILL.md), the
[walkthrough](examples/walkthrough.md) and [setup guide](references/setups.md).
Run `osr next` for the next required workflow action. Consult
[failure triage](references/failure-triage.md) for a blocked or failed task.

## Bugs and feature requests

Search existing issues, then use the
[issue forms](https://github.com/De-pitcher/orchestrator-supervisor-reviewer/issues/new/choose).
Include `osr --version`, the commit/tag, Python and OS versions, the exact command,
a minimal reproduction and the complete relevant error. Explain expected and
actual behavior. For proposals, describe the problem and compatibility/trust
impact rather than only a preferred implementation.

Share only the smallest redacted evidence needed. `.ai/` records and review packs
can contain source code, local paths, command output and private project data;
do not upload an entire directory without inspecting it. Never share approval
secrets, access tokens or private keys.

Security reports belong in the [private security channel](SECURITY.md), not
public issues. Conduct reports follow the [code of conduct](CODE_OF_CONDUCT.md).

Support is community/maintainer best effort. There is no paid support contract
or guaranteed response time. CI success applies to its tested commit and matrix,
not every integration, external harness or downstream project.
