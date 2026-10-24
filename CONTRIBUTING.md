# Contributing

OSR is in active development. Package metadata is at 0.3.1; current changes are documented under Unreleased in [CHANGELOG.md](CHANGELOG.md). Issues and pull requests are welcome.

## Ground rules

- **Keep the core idea intact:** the AI proposes, the tool decides. A change that lets an AI's claim count as evidence will not be accepted.
- **Stdlib only** for `scripts/osr.py`. No third-party dependencies, so it runs anywhere Python does.
- **Behavior changes need meaningful tests** in the relevant `tests/test_*.py` module. End-to-end CLI tests live in `tests/test_osr.py`; focused modules cover logs, authorization, test evidence, freshness and Git gates. Preserve both an attack/rejection case and a valid clean control.
- **Keep `SKILL.md` short.** Detail belongs in `references/`. Explain why a rule exists; models follow reasons better than commands.
- **Be honest in docs.** If a check has gaps, say so in `references/guarantees.md`.

## Running the tests

Run the affected module first. Keep local modules sequential and use isolated batches rather than a monolithic full-project command:

```powershell
python -m unittest discover -s tests -p test_run_logs.py -v
python -m unittest discover -s tests -p test_command_authorization.py -v
```

For end-to-end changes, run `python -m unittest discover -s tests -p test_osr.py -v` as one scoped process: its benchmark consumers share a cached report. Do not run a duplicate standalone benchmark afterwards. Run the other affected `test_*.py` modules separately as needed; a focused module alone is not complete integration evidence.

The current inventory is 251 tests. The GitHub Actions workflow runs full discovery, ledger verification and plan validation on Ubuntu, macOS and Windows with Python 3.8–3.12. Those matrix checks passed for commit `58a16e6`; local Windows/Python 3.14.3 evidence is separate. CI does not currently run a final repository acceptance audit or establish actor authentication. Check the current PR's results before merging.

## Good first contributions

- Reference checkers for more languages (`check_refs` in `osr.py`): Go, Rust, Java, C#.
- Better stack detection in `detect_commands`.
- Real-world feedback: which model, which tool, where did it skip, fake, or loop? Open an issue with the ledger excerpt (`.ai/ledger.jsonl`) and what you expected.
- Adapters for specific tools' instruction formats.
- Integrations that use the existing `--json` output mode and documented exit codes.

## Design questions open for discussion

- Making human-only commands cryptographically distinct (for example, a separate approval token) rather than honor-system.
- Mutation testing hooks as a first-class gate.
- Support for parallel tasks and multiple agents working at once (file locking on state).
