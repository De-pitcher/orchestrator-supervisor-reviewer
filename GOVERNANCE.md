# Governance and maintenance

OSR is a small, maintainer-led open-source project. The active repository
maintainer is [@De-pitcher](https://github.com/De-pitcher); file ownership is
recorded in [.github/CODEOWNERS](.github/CODEOWNERS). Contributions and
constructive technical disagreement are welcome.

## Decisions and changes

Use an issue for proposals that change observable behavior or trust boundaries.
Small fixes can go directly to a pull request. Explain the problem, constraints,
evidence and compatibility impact. Preserve attack tests and clean controls.
The maintainer decides what is accepted and performs merges into `main`.

Agent model names, reviewer labels and `--by` values are self-reported workflow
metadata. They do not authenticate a human or establish independent review.
Same-agent reviews must remain visible as such.

## Branch policy

`main` requires a pull request, up-to-date passing GitHub Actions checks and
resolved review conversations. Protection applies to administrators; force
pushes and deletion are disabled. The stable `ci-required` check summarizes the
complete test matrix. During its introduction, the existing 15 matrix contexts
remain required until the aggregate check has been verified successfully.

There is currently one collaborator. The maintainer explicitly chose **zero
mandatory independent approvals** so PRs authored under that account can still
be merged after CI and review. This is a solo-maintainer exception, not a claim
of independent approval. When another trusted reviewer is available, require at
least one approval and consider code-owner review. Do not add nominal reviewers
or misleading AI identities to simulate that separation.

`dev` is the integration branch; topic branches feed it before a maintainer
reviews a `dev` → `main` PR. Do not force-push shared history. Branch protection
is a GitHub setting, not a property that a local hook or policy file can enforce.
Repository administrators retain the ability to change those settings.

## Community and responsibility

- [Contribution guide](CONTRIBUTING.md): local checks and review expectations.
- [Code of conduct](CODE_OF_CONDUCT.md): behavior and private conduct reporting.
- [Security policy](SECURITY.md): private vulnerability disclosure.
- [Support](SUPPORT.md): questions, bug reports and feature requests.
- [Architecture](docs/ARCHITECTURE.md): where implementation and evidence live.
- [Release process](docs/RELEASING.md): what must be verified before publication.

Maintenance is best effort. There is no promised response time, support contract
or independent security certification. The MIT license and documented
[limitations](references/guarantees.md) remain applicable.
