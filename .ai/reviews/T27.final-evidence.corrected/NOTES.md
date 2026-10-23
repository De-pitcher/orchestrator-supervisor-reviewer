# T27 corrected final evidence — provenance notes

Builder-side pointers only; the supervisor should inspect the JSON/logs directly.

## Provenance

- Frozen governed tree digest: `fb0f2d19eb7a76a54aa0296ca923d9465f17aaca4a162116edc476a62f2c0fd4`
  (84 governed files, recorded in `freeze.json` / `freeze.manifest.json`).
  All eight supplementary batches and the formal verify report the same digest
  before and after execution.
- Schedule: `.ai/reviews/T27.schedule.json` (approved S1-S8 + FORMAL, 249 IDs).
  Inventory: `.ai/reviews/T27.inventory-before.json` (249 IDs).
- Result: supplementary 78, formal 171, union 249, disjoint, union equals the
  pre-edit inventory (`run-summary.json`).
- Earlier evidence is preserved unchanged in
  `.ai/reviews/T27.final-evidence/` and `.ai/reviews/T27.final-evidence.attempt-1/`.
  Both trees still self-verify: every `log_sha256` in the preserved
  `run-summary.json` files matches the `S*.log` bytes stored beside them, and the
  prior freeze digest is unchanged at
  `b17deff95afe64050a38b2d24c0181972d2831ab32f85cf1884d0cf5e5c696fd`.
- Provenance caveat for `T27.final-evidence.attempt-1/run-summary.json`: its
  `log` fields record the output-directory path as configured when that batch
  ran (`.ai/reviews/T27.final-evidence/S1.log`, ...), because the directory was
  subsequently renamed to `*.attempt-1` when the corrected run started. The
  sibling `S1.log`-`S4.log` files inside `attempt-1/` are the matching artifacts:
  each recorded `log_sha256` equals the SHA-256 of that sibling, not of the
  newer log now sitting at the old path. Treat the `log` string as historical
  metadata; the hashes are the authoritative link.

## S4 benchmark report (actual, not reconstructed)

- Runner: `.ai/t27_s4_runner.py`, argv
  `["C:\\Python314\\python.exe", ".ai/t27_s4_runner.py"]`, cwd repository root.
- Import paths: repository root and `tests` are both inserted explicitly, so
  `test_osr` resolves to the same module/class cache used by the unittest IDs.
- `OsrTests.benchmark_report()` was invoked once in that process
  (`benchmark_report_invocations: 1`); the three consumer tests then ran in the
  same process against cache key `None`
  (`S4.runner.json: cache_entry_is_returned_report: true`).
- Report: `S4.benchmark-report.json`, SHA-256
  `eb44be459d3d07dd7973e6608a459af34d671823d66dbd40e486e25663109820`,
  12/12 vectors caught, 11 clean canaries, 0 false positives, no known misses.
- No standalone benchmark was run after the final S4 batch.

## Documented parser limitation (observed, not fixed here)

The formal verify executed 171 IDs (per the five hash-checked tool logs) while
the ledger's `canonical_tests` recorded 148. The difference is the documented
verbose-unittest shape where a method docstring puts the identity and `... ok`
on separate lines. This is conservative missing evidence, disclosed in
README.md and references/guarantees.md. Extending the parser is out of scope
for T27.

## Corrections delta (11 authorized files)

tests/test_run_logs.py, tests/test_command_authorization.py,
tests/test_test_evidence.py, tests/test_osr.py,
tests/test_hardening_hypotheses.py, tests/test_tautological_ast.py,
tests/test_zero_runner.py, evals/eval_suite.py, README.md,
references/guarantees.md, integrations/README.md.

The first three are the explicitly authorized fixture-setup migrations; the
guardrails in `.ai/reviews/T27.fixture-preflight.md` apply to them.

## Pre-freeze validation runs (not evidence)

The corrected fixture changes and the S4 runner were smoke-validated once in
scratch directories before freezing:
`.ai/reviews/T27.scratch-s4/` and `.ai/reviews/T27.scratch-validate/`.
Those directories are retained but are not part of this evidence. The retained
reports/logs in this directory all come from the post-freeze final schedule.
