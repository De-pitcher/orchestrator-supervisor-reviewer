# Release process

There are no published GitHub releases when this process is introduced. Current
package metadata is 0.3.1; Unreleased changes and a branch named v0.3.2 do not
constitute a release. Publication is a separate maintainer decision.

## Before a release

1. Agree the release scope and support expectations in an issue/plan. Document
   breaking behavior and remaining limits instead of implying security certification.
2. Use a scoped task to align `VERSION` in `scripts/osr.py`, `pyproject.toml`,
   changelog entries and public documentation. Do not bump a version as part of
   unrelated fixes or fabricate a past publication date.
3. Run approved local modules sequentially, retaining meaningful red/green
   evidence. Benchmark consumers share one report per process; do not rerun an
   unchanged benchmark merely for paperwork.
4. Require the full hosted matrix and `ci-required` to pass on the release PR,
   resolve conversations and have the human maintainer merge it into protected
   `main`. State which platforms were actually checked.
5. Review release contents for secrets, private project data and accidental
   scratch files. Preserve any required evidence bytes and provenance.

## Distribution boundary

The supported skill installation is a source checkout containing `SKILL.md`,
`scripts/`, `assets/`, `references/` and the relevant integration files.
`pyproject.toml` currently declares the standalone `osr` module/entry point; it
does not establish that a wheel contains the whole skill or its templates.

Before advertising a PyPI/wheel installation as a complete skill, separately
implement and verify artifact contents, clean-environment install, CLI startup,
initialization with the intended templates and uninstall behavior. That packaging
work is not delivered by this repository-governance change. Do not use a successful
source-tree test run as a substitute for distribution testing.

## Publication

After those gates, the maintainer chooses an explicit version tag on the reviewed
`main` commit and creates a GitHub release with notes, known limits and verified
artifact digests. A Git tag alone does not publish a package. No automatic PyPI
upload or release-on-push workflow is configured by this change. Define credentials,
trusted publishing, artifact checks and maintenance/backport policy before adding
such automation. Never embed publishing credentials in repository files.
