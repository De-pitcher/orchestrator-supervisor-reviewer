<!-- Save as .ai/reviews/<TASK>.quality.md  then run:  osr review <TASK> quality --reviewer <your-model-name>
     Review the CHANGED files only, as a skeptical senior engineer who did not write them.
     Every check needs a note naming what you actually inspected. NA needs a reason. -->
C1: PASS - grepped every import and called function in the changed files; all exist in the repo or package.json
C2: PASS - empty input, None, and oversized input are handled in parse() lines 30-55
C3: NA - no user input, network, or file access in this change
C4: PASS - no TODO, stubs or elided code in the diff
C5: PASS - callers of format_name() in 3 files still match the unchanged signature
C6: PASS - new tests assert exact outputs; no skips; assertion count rose from 4 to 9
C7: PASS - naming and error style match neighbouring modules
C8: PASS - only files named in allowed_files changed

## Seams
<!-- Required ONLY if the task card declares seams:.
     For each declared seam, list every external field or call the code uses,
     each cited as:
     SEAM <seam-id>: @ <authoritative-source-path>:<line> "exact snippet"
     pointing directly into the authoritative upstream source.
-->
SEAM <seam-id>: @ <authoritative-source-path>:<line> "<exact snippet>"

## Realtime Appendix
<!-- Required ONLY if the task card declares kind: realtime.
     Address each lifecycle and timing invariant concretely:
     - Teardown: which close codes or signals are sent, and does reconnect distinguish user-intentional stop from failure?
     - Backpressure: can a burst saturate network or memory buffers, and are there asynchronous yields?
     - Race windows: what happens if an event arrives while a prior socket or transaction is draining?
     - Time drift: do metrics accumulate real deltas or flat increments?
-->
- Teardown: <close code/signal details and user-intentional stop vs failure handling>
- Backpressure: <buffer saturation limits and asynchronous yield points>
- Race windows: <behavior during drain windows and overlapping arrivals>
- Time drift: <monotonic delta accounting versus flat increments>

BREAK_ATTEMPTS:
- Pass a 10 MB string to parse(); check it does not load everything into memory twice
- Call format_name() with surrogate-pair emoji and confirm no crash or truncation
- Run the new test twice in a row to detect hidden shared state between runs

VERDICT: PASS
