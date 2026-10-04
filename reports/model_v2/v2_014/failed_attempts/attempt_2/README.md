# V2-014 clean-clone attempt 2 -- harness/verifier evidence-assembly defect; NOT the canonical proof

Target: method commit `02e30d306450862e12a000e50a385c5c4858bd45`. A brand-new clone, fresh venv and
`npm ci`; no file edited or copied in. ALL checks and steps passed (V2-013 replay 93 windows
80x200/13x422 digest 7ef39ae9..., flatline replay 17 windows 6x422, 2343-node chunked + monolithic
regression, frontend 68 tests, complete V2-FL-005 reproduction, ruff, pip check, zero tracked drift).
Defects found AFTER the run when the evidence was dry-imported (uncommitted, removed again) into the
development checkout to exercise the verifier:
 1. the orchestrator's reproducibility manifest looked up `synthetic_fl` instead of the evidence file
    `synthetic-fl`, leaving the V2-FL-005 cohort/final-state/digest fields null;
 2. the evidence verifier read the same wrong file name and split the node list on whitespace
    (node ids contain spaces) instead of on lines.
Both are evidence-assembly defects in the (bound) harness/verifier, not repository, dependency or data
defects. Protocol section 42: the clone is not repaired or reused; the harness was corrected
prospectively, re-frozen, committed, and an entirely NEW clone is used.
