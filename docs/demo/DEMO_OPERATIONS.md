# Demo operations: restart-proof state, separated demo data, preflight

These three additions remove the failures most likely to hurt a live demonstration. Nothing here changes scientific behaviour, and the defaults are unchanged.

## 1. Keep runs and History across restarts: `--durable`

By default every launch uses a fresh temporary workspace (`nhm-faculty-demo-*`), so runs, journals, figures, History sessions and exports disappear at the next restart. Only engineering candidates
(`data/studio_candidates`) survive.

```bash
PYTHONPATH=src:. python -m scripts.run_nhm --durable            # ~/.nhm/demo_workspace: created on first use, resumed afterwards
PYTHONPATH=src:. python -m scripts.run_nhm --durable ~/nhm_demo   # or any directory outside the repository
PYTHONPATH=src:. python -m scripts.run_nhm --demo --durable       # offline demonstration authentication, same durable workspace
```

* Runs belong to the account that created them, so **prepare by doing**: launch with `--durable`, sign in as the demo account, run the demonstration flow once (a realistic 3-round run, a run started from its
  candidate, a recorded-hardware pipeline run). They are still there, with their replays, after a restart; they are your "prepared run" fallbacks.
* A run that was in progress when the site stopped is reported FAILED (`INTERRUPTED_BY_RESTART`), never presented as a result.
* To start clean: stop the site and delete the workspace directory. Without `--durable` nothing changes.

## 2. Keep generated demo data out of the real device database: `NHM_HARDWARE_DEMO_DATABASE`

The prerecorded showcase sessions are generated, not recordings. By default their collections (`demo_prerecorded_hardware_session_*`) are created in the same database as real device telemetry.
Set a separate database to stop mixing them:

```bash
NHM_HARDWARE_DEMO_DATABASE=nhm_demo    # in .env; unset = same database as before
```

Only the showcase collections move (seeded there when missing, never overwritten). Live monitoring and History import of `records_YYYY-MM-DD` keep reading the main database. Existing demo collections in the
main database are left as they are and are simply no longer read. Never place generated data in a `records_*` collection: it would be indistinguishable from a device recording.

## 3. Check everything first: `scripts/demo_preflight.py`

```bash
PYTHONPATH=src:. python -m scripts.demo_preflight --workspace ~/.nhm/demo_workspace
```

Read-only; prints PASS / WARN / FAIL per check and exits 1 only on FAIL. It checks Python 3.11, node and `node_modules`, the three ports (FAIL when an earlier site still holds them), Clerk keys (never printed)
and Clerk host reachability (WARN with the offline fallback `--demo`), MongoDB reachability and whether demo data shares the real database, the `MODEL_V2_FINAL` checkpoint digest against its manifest, key frozen
evidence files, the workspace state (what a restart will do), the candidate library and free disk.

Run it before the session, and again after a restart.

## Fallbacks (nothing is substituted silently)

| Situation | Action | What the audience sees |
|---|---|---|
| Clerk host unreachable | launch with `--demo` | "OFFLINE DEMO" authentication banner |
| Hardware / MongoDB unreachable | continue; the hardware source is simply unavailable | recorded sessions and prepared runs, labelled |
| A live run takes too long | open the prepared run from the durable workspace | its normal Live page with the RECORDED / replay labels |
| A run record is missing | open a stored candidate from the Models page and start a run from it | the candidate's cohort, source and digest |

## Guided demonstration path

`/app/demo` (Overview → "GUIDED DEMONSTRATION PATH") is the recommended story: scope, Monitor, a live 3-round realistic-cohort federation run, per-round evaluation, the frozen scientific result, the candidate library, the hardware boundary, and limits. Every step names how its evidence is produced (computed now, a prepared recorded run, frozen evidence, a stored session, or the stored library) and gives a fallback, so a replay is never presented as live. The older evidence tour and run storyboard remain as detailed companions. The steps are data in `frontend/src/lib/product/demo-path.ts` and are covered by `demo-path.test.ts`.

## 4. Presenting from the Guided demo page (`/app/demo`)

The page is built to be presented from. **Start presenting** opens a presenter bar with a timer, the current step and its planned start time, an on-pace / ahead / behind indicator, and controls: arrow keys move between steps (moving on ticks the step you leave as covered), space pauses the timer, Escape stops. The story map shows the eight steps proportional to their planned minutes; every step card has Do / Understand / Say / If it fails, its evidence mode (live, prepared run, frozen evidence, recorded session, stored library or statement) and a link that opens the page. Covered ticks are remembered in the browser only (never sent anywhere). The page also lists the pre-flight and launch commands with copy buttons.

Rebuilding the frontend while the site is running deletes the files its preview server is serving and takes the whole stack down: stop the site first, then build.
