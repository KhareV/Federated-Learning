# Original Federation Studio — preservation checklist (reference: `docs/unified_live_fl/baseline/`)

Captured at `06bd9a0` + docs only, DemoAuth, real 3-round LIVE_RUN `FEDRUN-D4C404C2AB81` (203 events, 24 accepted updates, 0 console errors), widths 1440/1024/768/390, no horizontal overflow at any width. Screenshots: `entry_*`, `live_midrun_1440`, `live_completed_*`, `live_client_selected_1440`; machine summary `baseline_report.json`.

Must be identical after the change (compare by screenshot + DOM test ids):
- [ ] `/app/federation/live` section order: header, run chips/counters, STAGES stepper, CLIENT NETWORK, round progress + protected-aggregation, model state + candidate lifecycle, timeline.
- [ ] `data-testid` hooks: `client-network`, `coordinator`, `client-grid`, `run-status`, `update-ready-count`, `submitted-count`, `round-states`, `secagg-status`, `owner-card-label`, `my-participation`.
- [ ] Eight client cards on the radial layout around the COORDINATOR hub; each shows state, local examples, milestone, update digest.
- [ ] ★ MY EDGE CLIENT (SIM_FL_SITE_00) appears **only** for CLERK + LIVE_RUN (`ownerBoundClientId`); in DemoAuth and REPLAY it is absent — baseline confirms this (`star:false`). It cannot be visually verified without connected Clerk.
- [ ] Replay note, stream-error banner, FederationBanner, privacy/engineering-only disclosures.
- [ ] Entry page: pipeline, lanes, run form (3 rounds default), clients, runs list, technical evidence.
- [ ] Styling: existing dark theme tokens; no new design system.
