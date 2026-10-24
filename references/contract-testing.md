# Contract Testing, Fixtures, and Seams

## The Problem
When building services or clients across component boundaries (seams), tests often pass with fabricated mocks. A builder writing both the consumer logic and its mock operates under a single set of assumptions. If the upstream provider uses different field names (e.g. `user_id` vs `id`), the tests pass locally, but production fails on integration.

## Iron Principle
**Do not let the builder invent response shapes.**
Every seam must either be anchored to authoritative schema definitions or to real, captured fixtures.

---

## 1. Schema-Driven Generation (Preferred)
Generate consumer types directly from the provider's authoritative schema:
- **TypeScript**: `openapi-typescript`, `protobuf-ts`, shared `@types` packages.
- **Python**: `datamodel-code-generator`, Pydantic models from OpenAPI/JSONSchema.
- **Go / Rust**: code generation from protobuf or OpenAPI specs.

When fields change upstream, schema regeneration causes compiler or typecheck errors (`tsc --noEmit`, `mypy`) before tests even run.

---

## 2. Recorded Fixtures (`osr fixture-add`)
When schemas are unavailable or dynamically defined, record fixtures from real traffic (staging curl, network capture, integration run) and register them with `osr`:

```bash
osr fixture-add tests/fixtures/user_101.json --seam user-api --source "captured from staging GET /api/v1/users/101 on 2026-10-21"
```

This command records:
1. Relative path to the fixture file.
2. The seam ID it anchors.
3. Cryptographic sha256 hash of the fixture file.
4. Capture provenance and timestamp in `.ai/state.json` and `.ai/ledger.jsonl`.

### Fixture Integrity
During `osr verify`, `osr` checks:
- Every fixture listed on the task card (`fixtures: ...`) is registered.
- The file on disk matches its registered sha256. Tampering with or altering a fixture without re-registration fails verification.

---

## 3. Conformance Commands
For seams with validation tooling, declare a `conformance:` command on the task card or in `PLAN.md`:
```yaml
conformance: tsc --noEmit
# or
conformance: python -m pytest tests/test_conformance.py
```
The command must be confirmed in `.ai/config.json` and must pass during `osr verify`.

---

## 4. Heuristic Gate: `unanchored-mock`
If a task card declares `seams:`, any changed test file containing mock constructs (`unittest.mock`, `jest.mock`, `vi.mock`, `msw`, `nock`, `@patch`, `responses`) is flagged as `unanchored-mock` unless:
1. The test loads a registered fixture file, or
2. An authorized human operator issues a waiver:
   ```bash
   osr waive <task> unanchored-mock --reason "unit test uses synthetic mock" --approved-by <human-name>
   ```

> [!NOTE]
> The `unanchored-mock` check is a deterministic heuristic designed to force explicit awareness of synthetic mocks at seam boundaries. It does not replace end-to-end integration or contract testing.
