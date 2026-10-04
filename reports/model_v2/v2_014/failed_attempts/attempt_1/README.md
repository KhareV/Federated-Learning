# V2-014 clean-clone attempt 1 -- FAILED (harness-ordering defect); NOT the canonical proof

Target: method commit `3ce1870df50e27bc37187a90aeb1cad57cfce526`. A brand-new clone, fresh venv and
`npm ci` were used; no file was edited or copied in. Every check PASSED (inventory, artifacts, MODEL_V2
fixed vectors in two fresh processes, CAL_V2, gateway identity + semantic re-export, FL_INIT_V2 x2,
data-free FL development and held-out reconstruction, SecAgg data-free, complete V2-FL-005 synthetic
reproduction, lifecycle, 2343-node chunked + monolithic regression, ruff, pip check, frontend
68 tests / 0 svelte-check errors / build, zero tracked-file drift) EXCEPT the two V2-013 software replays:
the harness ran them BEFORE `npm ci`, so `npm run build` exited 127 (frontend not installed).
This is a harness defect, not a repository/dependency defect. Per protocol section 42 the clone was
not repaired; the harness order was corrected prospectively (frontend install first), a new method
commit was made and an entirely NEW clone is used for the canonical proof.
