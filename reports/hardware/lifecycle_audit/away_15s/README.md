# Monitor lifecycle audit (away 15 s) — evidence

Level: VERIFIED_LOCAL_RENDER_REPLICA (ESP32 emulator -> local replica -> Atlas `nhm_rehearsal`; real Chrome + Clerk).
Physical ESP32 and deployed Render: NOT verified.

* `away_lifecycle_verdict.json` — PASS verdict (attempt 2); `away.json` — raw driver output; `away_shots/away_*.png` — validation screenshots.
* `away_shots/HISTORICAL_FAILURE_attempt1_clerk_signin_timeout.png` — **a FAILURE, not validation.** Attempt 1 stopped at the
  Clerk password step ("Clerk sign-in timeout", transient dev-instance stall) before any monitoring step ran. It is kept only
  as a record that the first attempt failed; the retry (attempt 2) produced the passing evidence.
