# UI-ENH-003 initial bug inventory

Inspected the current offline DEMO application before UI edits: attached and connected the virtual wearable, completed a monitoring session, opened its persisted history, and visited 15 product routes at desktop/mobile widths. No page-level horizontal overflow or browser console errors were observed. The following are actionable presentation issues, not backend defects.

| Class | Route/component | Problem and reproduction | Minimal fix |
| --- | --- | --- | --- |
| STATE PRESENTATION | Device | Before and after connection, metadata and raw connection-state IDs dominate the current lifecycle; `CONNECTED` does not visually lead to the monitoring action. | Add a clear simulated-only summary and current-step lifecycle, retain exact metadata in secondary disclosure, elevate the monitoring link. |
| LOADING / EMPTY STATE | Device | Initial async device load briefly presents the same “no device” state as a settled empty result. | Distinguish loading from settled empty; explain next action. |
| RESPONSIVE | History | Nine-column nowrap table forces horizontal reading at 390 px despite no document overflow. | Retain semantic desktop table; render equivalent stacked mobile cards. |
| LOADING / EMPTY STATE | History | Empty table state has no loading distinction; action is inline text. | Show persisted-session loading and clear monitoring CTA. |
| VISUAL CONSISTENCY | History detail | Session runtime facts and raw JSON events are visually similar in priority. | Add overview hierarchy and put verbose event payloads behind per-event technical disclosures while preserving time-domain separation. |
| COPY / TERMINOLOGY | Federation Privacy | Narrow SecAgg and unsupported privacy claims are present but not visually separated; production-security certification is not explicit. | Use a local/coordinator/shadow/not-claimed sequence and prominent negative-claim panel. |
| RESPONSIVE / NAVIGATION | RunList | Run IDs and technical mode/status badges lead every row and wrap densely on mobile. | Lead with LIVE RUN/REPLAY, status, round and algorithm; disclose IDs/timestamps and keep full values accessible. |
| LAYOUT | Federation run configuration | Final 1440/390 screenshots exposed overlapping field labels and select boxes in the existing run form. | Use explicit label text elements and a vertical flex layout; do not change run choices or submit behavior. |
| EMPTY STATE | RunList | “No federation runs yet” does not tell the user how to start. | Link to configured live-run entry point without implying REPLAY trains. |
| VISUAL CONSISTENCY | System | Raw key/value dump is the entire page. | Add typed summary using only existing system response fields and preserve raw response under disclosure. |
| VISUAL CONSISTENCY | About | One long list makes distinct claim boundaries hard to scan. | Group the unchanged claims into scope/runtime/federation/not-claimed sections. |
| ACCESSIBILITY / NAVIGATION | ProductShell | Mobile drawer lacks Escape-to-close and focus is not explicitly restored; long identity can compete with controls. | Add presentation-only Escape/focus behavior and constrain identity width; preserve auth/sign-out semantics. |
| RESPONSIVE | History desktop table | The Evidence action was hidden to the far right of the scrollable desktop table at 1440 px. | Move the action immediately after session/state; retain all technical columns. |

The initial browser harness itself recorded a false negative: `about:blank` produced an empty hostname, and `aria-expanded` was sampled before Svelte updated. Those are test-harness timing/filter issues, not product bugs; the final harness will exclude non-HTTP hostnames and wait for the drawer update.
