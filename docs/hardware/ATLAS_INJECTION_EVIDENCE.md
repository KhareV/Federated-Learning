# Atlas injection evidence — 2026-10-14 UTC

Real MongoDB Atlas test collection: `health_db.nhm_integration_test`. The test publisher identified every document with a unique run tag and deleted **13 of 13** inserted records after assertions. The final verification returned `PASS` for the Atlas-backed service path.

Session ID: `HW-60e8ac8ce8a64e3a90c253bcd2e002f9`. Five inserted BSON ObjectIds mapped to accepted session readings:

| MongoDB `_id` | ECG ADC value | BPM |
| --- | ---: | ---: |
| `6acf70382d8ad02837b77e10` | 1900 | 68 |
| `6acf70382d8ad02837b77e11` | 1973 | 69 |
| `6acf70382d8ad02837b77e12` | 2046 | 70 |
| `6acf70382d8ad02837b77e13` | 2119 | 71 |
| `6acf70382d8ad02837b77e14` | 2192 | 72 |

The pre-session document `6acf70372d8ad02837b77e0f` was excluded. Invalid ECG document `6acf70382d8ad02837b77e15` was excluded. The test also inserted records with missing ECG and missing timestamp; both were excluded. Device-reported zero vital values became unavailable. A delayed timestamp retained its stored time. A second poll did not replay records. After 5.2 seconds without accepted data, the session reported `STALE DATA`; another insertion recovered it. After stop, `6acf703e2d8ad02837b77e1b` was excluded from the stopped session. History count and first reading survived a service restart. A second user was denied the session. The test collection had zero remaining tagged synthetic records after cleanup.

The full product application factory was also started in explicit demo-auth test mode with this test collection; its hardware REST start, poll, stop, and history routes each returned HTTP 200. That isolated API test was **not** a Clerk browser result or a physical ESP32 result. A subsequent authenticated Clerk browser run captured screenshots separately. The real production collections contained no new record after `records_2026-10-13` at the time of verification.

## Final reader regression rerun

After the rollover and duplicate-count fixes, `python -m scripts.verify_hardware_atlas` passed again against the real Atlas test collection. Session `HW-c13c6f75ff9a4b3c8697b4ae4f49e4d5` accepted seven test readings and excluded the pre-start, malformed, and post-stop documents. The first five accepted `_id` → ECG/BPM mappings were `6acfb8c1b228cef20bcc4b9c` → 1900/68, `6acfb8c1b228cef20bcc4b9d` → 1973/69, `6acfb8c1b228cef20bcc4b9e` → 2046/70, `6acfb8c1b228cef20bcc4b9f` → 2119/71, and `6acfb8c1b228cef20bcc4ba0` → 2192/72. Stale state, recovery, owner isolation, fresh high-water mark, and restart history passed. Exactly 13 of 13 inserted test documents were removed by ID; no production collection was modified. The separate authenticated browser result and waveform geometry are recorded in `reports/hardware/browser/verification.json`.
