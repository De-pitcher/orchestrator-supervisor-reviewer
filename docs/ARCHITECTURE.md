# Architecture and repository map

OSR is a source-distributed skill with a standard-library Python enforcement
CLI. It deliberately separates agent proposals from tool-recorded evidence.
This map describes the current layout, not a promised package refactor.

## Components

| Location | Responsibility |
|---|---|
| `SKILL.md`, `PROMPT-ONLY.md`, `references/` | Agent workflow and its weaker manual fallback |
| `scripts/osr.py` | CLI parsing, card/plan validation, command execution, review gates, persistence and audit |
| `assets/` | Plan, task and review templates for source-checkout use |
| `tests/` | End-to-end workflow, focused regressions and adversarial controls |
| `evals/` | Attack vectors and clean canary benchmark reporting |
| `integrations/` | Configured harness interception and read-only Git hooks |
| `.github/` | Hosted CI, contribution intake, ownership and dependency-update configuration |
| `.ai/` | This repository's self-hosted workflow, accepted history and selected evidence |
| `docs/planning/`, `docs/evidence-hardening/` | Historical proposals, activation and implementation records |

The core CLI is currently one module. Runtime behavior should not be moved merely
to make directories look conventional: a future split needs a separate approved
plan, compatibility boundaries and equivalent adversarial evidence.

## Evidence flow

1. Confirmation binds an exact command to successful recorded output.
2. Human approval binds the plan/configuration and a governed baseline.
3. A task start binds its card and accepted starting map; one task is active.
4. Verification captures exclusive per-command logs and their byte digests,
   checks current canonical test evidence and rejects governed test-time writes.
5. Reviews bind to the verified task/start lineage; completion records a delta.
6. Audit replays accepted deltas and compares current content without rerunning
   configured tests. The Git helper then compares governed index bytes and
   required governance evidence against the audited working artifact.

Hashes and locks are not actor authentication or an atomic multi-file database.
Read [the limits](../references/guarantees.md) before changing a gate. Review
[contribution expectations](../CONTRIBUTING.md) and preserve both attack and clean
controls. Historical `.ai/` files are not application runtime configuration for
a newly adopted downstream project; initialize that project's own workflow.
