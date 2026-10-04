# V2-014 handoff (gate V2G13: PASS) -- reproducibility verification only

Chronology: entry 3d0e9d4 -> method commits 3ce1870 / 02e30d3 / daf9053 (final method commit; two earlier clone
attempts FAILED on harness defects and were discarded, see failed_attempts/) -> clone 1 of daf9053 PASS
-> result transition 209fdeb -> clone 2 of 209fdeb (final-commit verification) PASS -> this evidence-only
commit. Clone 1: brand-new git clone, fresh Python 3.11 venv from requirements-dev.lock, fresh `npm ci`,
isolated HOME, no copied source/data, no rescue install; 2343 nodes (2323 passed, 14 DATA_GATED + 6 other
skips, 0 failed); V2-FL-005 final state 3f0b7762...; digest e234b755.... No scientific claim is made; MODEL_V1
remains the operational default; the release/default decision is NOT started.
