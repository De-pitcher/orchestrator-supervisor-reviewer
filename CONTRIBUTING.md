# Contributing

This project is early (v0.1) and meant to be refined in the open. Issues and pull requests are welcome.

## Ground rules

- **Keep the core idea intact:** the AI proposes, the tool decides. A change that lets an AI's claim count as evidence will not be accepted.
- **Stdlib only** for `scripts/osr.py`. No third-party dependencies, so it runs anywhere Python does.
- **Every behavior change gets a test** in `tests/test_osr.py`. The tests drive the CLI the way an AI agent would, including the ways it tries to cheat. A new gate needs a test that tries to get around it.
- **Keep `SKILL.md` short.** Detail belongs in `references/`. Explain why a rule exists; models follow reasons better than commands.
- **Be honest in docs.** If a check has gaps, say so in `references/guarantees.md`.

## Running the tests

```
python -m unittest discover -s tests -v
```

## Good first contributions

- Reference checkers for more languages (`check_refs` in `osr.py`): Go, Rust, Java, C#.
- Better stack detection in `detect_commands`.
- Real-world feedback: which model, which tool, where did it skip, fake, or loop? Open an issue with the ledger excerpt (`.ai/ledger.jsonl`) and what you expected.
- Adapters for specific tools' instruction formats.
- A `--json` output mode for harnesses.

## Design questions open for discussion

- Making human-only commands cryptographically distinct (for example, a separate approval token) rather than honor-system.
- Mutation testing hooks as a first-class gate.
- Support for parallel tasks and multiple agents working at once (file locking on state).
