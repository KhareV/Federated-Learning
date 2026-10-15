# Site-wide UI tour: findings and fixes

Method: `python -m scripts.verify_hardware_connected_browser --producer ws --users-file <users.json> --ui-tour` seeds a recorded session and a
hardware run through the ESP32 emulator, then visits 27 routes at 1440 px and 390 px in real Chrome with a real Clerk session, recording
horizontal overflow, console errors, long paragraphs, sub-10.5 px text, unnamed controls and a full-page screenshot per route/viewport.

| Finding | Fix |
|---|---|
| "Fixed configuration" tiles overlapped the run form (Tailwind `.fixed`) | class renamed / neutralised |
| History table cut off the "View evidence" action at 1440 px | 10 columns reduced to 7 (stacked recording/signal), actions always visible |
| Hardware session detail listed all stored readings (8,366 words) | summary tiles + collapsed list (first/last 25) + "use in a federation run" |
| Generalisation requests returned 409 on hardware runs (console noise) | skipped; tab states "not applicable" |
| Panel eyebrow/note text 7 px, low contrast | 10.5 px, higher contrast (shared `Panel`, shell, tiles, studio panels) |
| Federation page opened with two long explainers before the Start card | collapsed "How federated training works" (still in the DOM) |
| Static "synthetic clients" copy while Recorded hardware was selected | pipeline, lanes, banner and clients panel follow the chosen data source |
| Client history / round table used `SIM_FL_SITE_xx` for hardware runs | data-source aware |
| Long paragraphs (> 45 words) on Model and Storyboard | collapsed behind a plain label (`ReadMore`) |

Not changed, by design: the original Live-page components remain pinned by `preservation.test.ts` (original test ids and style rules
intact; the two components that gained the optional `dataSource` prop are digest-pinned).
Known, benign: the history detail route is served with the SPA fallback status (404) before client routing; no user-visible failure.
