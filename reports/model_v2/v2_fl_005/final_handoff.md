# V2-FL-005 handoff (gate V2FLG4: PASS) -- ENGINEERING ONLY

Cohort manifest SHA `ac7a207577394ca5c434b2d8a87989c6eaa77367826fcf13c47d54d8cd03e378`.

| client | source records | windows | VALID | DEGRADED | UNUSABLE | trainable | synthetic pos | synthetic neg | dataset SHA |
|---|---|---|---|---|---|---|---|---|---|
| SIM_FL_SITE_00 | 172800 | 93 | 93 | 0 | 0 | 93 | 20 | 73 | `fca4470983fe` |
| SIM_FL_SITE_01 | 172771 | 93 | 91 | 2 | 0 | 91 | 20 | 71 | `b3e6499a7404` |
| SIM_FL_SITE_02 | 172656 | 93 | 91 | 0 | 2 | 91 | 19 | 72 | `ac986172820b` |
| SIM_FL_SITE_03 | 172800 | 93 | 89 | 0 | 4 | 89 | 18 | 71 | `e54f4da26b97` |
| SIM_FL_SITE_04 | 172800 | 93 | 90 | 0 | 3 | 90 | 19 | 71 | `89d34fb72f6e` |
| SIM_FL_SITE_05 | 172800 | 93 | 93 | 0 | 0 | 93 | 20 | 73 | `ed97214e3542` |
| SIM_FL_SITE_06 | 172800 | 93 | 93 | 0 | 0 | 93 | 20 | 73 | `a1c40334c3a4` |
| SIM_FL_SITE_07 | 172627 | 93 | 83 | 2 | 8 | 83 | 14 | 69 | `9dbe85276d96` |

3 rounds x 8 clients, 24/24 updates accepted (24 engineering local-training calls, 0 scientific fits);
4 injected round-3 attempts rejected (STALE_ROUND, DUPLICATE_UPDATE, BASE_STATE_MISMATCH,
UNKNOWN_CLIENT); exactly-once commits and arrival-order canonicalization verified; restart/resume
final SHA equals the uninterrupted run; two fresh-process full runs and the control-plane event replay
are identical; one-round Flower SecAgg+ shadow (max_weight 256, disclosed pre-freeze rule) max abs
6.3e-6 / relative L2 1.35e-5, plain clear updates 8, protected 0; 723 finite-logit windows, no
metrics. Pre-freeze dry runs (including the failed max_weight=4096 shadow) are disclosed in
`pre_freeze_disclosures.json`. Regression: 2336 nodes, 30 chunks,
0 failed; ruff and pip check PASS. CI never queried or triggered.
