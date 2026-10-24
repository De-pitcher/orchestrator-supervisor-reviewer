# Audit  (2026-10-24T00:32:19Z)

Ledger integrity: ok. Plan approved and unchanged: True.

## Freshness

- Approval epoch: 298
- Baseline: 84 governed files, digest 03c2b33a7f2a5eb111e143d90523ba4c0c4bc4d659fb26a4506dd951b1ec39e6
- Accepted map: 84 governed files, digest 86dc8086e8c449cb54f035daabe753a70a1b0eab27060922f9d886466941cce6
- approval epoch 298 baseline: 84 governed files

### Archived history (disclosed, no current credit)
- T1 attempt 1 at seq 10 is archived history; it supplies no current requirement credit
- T2 attempt 1 at seq 17 is archived history; it supplies no current requirement credit
- T3 attempt 1 at seq 24 is archived history; it supplies no current requirement credit
- T4 attempt 1 at seq 31 is archived history; it supplies no current requirement credit
- T5 attempt 1 at seq 38 is archived history; it supplies no current requirement credit
- T6 attempt 1 at seq 46 is archived history; it supplies no current requirement credit
- T7 attempt 1 at seq 56 is archived history; it supplies no current requirement credit
- T1 attempt 1 at seq 72 is archived history; it supplies no current requirement credit
- T2 attempt 1 at seq 79 is archived history; it supplies no current requirement credit
- T3 attempt 1 at seq 87 is archived history; it supplies no current requirement credit
- T4 attempt 1 at seq 98 is archived history; it supplies no current requirement credit
- T5 attempt 1 at seq 109 is archived history; it supplies no current requirement credit
- T6 attempt 1 at seq 116 is archived history; it supplies no current requirement credit
- T1 attempt 2 at seq 150 is archived history; it supplies no current requirement credit
- T2 attempt 1 at seq 162 is archived history; it supplies no current requirement credit
- T3 attempt 1 at seq 175 is archived history; it supplies no current requirement credit
- T4 attempt 1 at seq 187 is archived history; it supplies no current requirement credit
- T5 attempt 1 at seq 195 is archived history; it supplies no current requirement credit
- T6 attempt 1 at seq 207 is archived history; it supplies no current requirement credit
- T22 attempt 1 at seq 250 is archived history; it supplies no current requirement credit
- T23 attempt 1 at seq 264 is archived history; it supplies no current requirement credit
- T24 attempt 1 at seq 272 is archived history; it supplies no current requirement credit
- T24 attempt 1 at seq 284 is archived history; it supplies no current requirement credit
- T25 attempt 1 at seq 297 is archived history; it supplies no current requirement credit

## Requirement traceability

| Req | Check | Tasks | Status | Evidence |
|---|---|---|---|---|
| R20 | auto | T27 | VERIFIED | scripts/osr.py:936 |
| R21 | auto | T27 | VERIFIED | scripts/osr.py:795 |
| R22 | auto | T27 | VERIFIED | scripts/osr.py:1509 |
| R23 | auto | T27 | VERIFIED | scripts/osr.py:2732 |
| R24 | auto | T26,T27,T29 | VERIFIED | integrations/git/pre_commit.py:534 |
| R25 | auto | T27,T28,T29,T30,T31 | VERIFIED | tests/test_osr.py:197 |

## Waivers (decisions to bypass a flag)
- T1 unanchored-mock:tests/test_hardening_hypotheses.py: tests/test_hardening_hypotheses.py is the Phase B adversarial test suite testing mock evasion across hypotheses, not an unanchored mock for T1 (approved by AI only)

## Self-reviewed (implementer == reviewer)
T1, T2, T24, T28, T29, T30, T31, T4, T5, T6
