<!-- Save as .ai/reviews/<TASK>.spec.md  then run:  osr review <TASK> spec --reviewer <your-model-name>
     Rules: one line per requirement of the task. PASS needs evidence copied from the real file (the tool checks it).
     FAIL and UNVERIFIED need a reason. Requirements marked "Check: manual" can only be UNVERIFIED. -->
R1: PASS @ src/feature/api.py:42 "exact code text from that line or the 3 lines around it"
R2: FAIL - the empty-input case returns None instead of raising ValueError as the AC requires
R3: UNVERIFIED - needs a human to judge the layout on a real device

VERDICT: FAIL
