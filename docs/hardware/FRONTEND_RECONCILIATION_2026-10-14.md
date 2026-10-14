# Frontend successor reconciliation, 2026-10-14

Baseline: `1501c9de890342d7aa286ed3521053799b48e81e` (`HEAD` and `origin/main` at audit start). The Studio successor was the accepted frontend tip. The 13 files below differed from that tip before this verification turn. Each diff was read and classified; none was dropped.

| File under `frontend/src/` | Classification | Reconciliation |
| --- | --- | --- |
| `lib/components/product/HardwareMonitor.svelte` | Hardware telemetry | New owner-scoped controls, honest states, stored ECG/vitals and source disclosure. Fixed the pre-start source wording and exposed exact latest document ID/ECG. |
| `lib/product/__tests__/socket-store.test.ts` | Existing Clerk/WebSocket | Tests first-frame token and reconnect behavior; retained. |
| `lib/product/__tests__/support.ts` | Hardware telemetry | Added fake API methods for hardware session tests; retained. |
| `lib/product/api.ts` | Mixed | Added typed hardware REST methods; retained the earlier no-token-in-URL Clerk WebSocket contract correction. |
| `lib/product/auth.ts` | Existing Clerk/WebSocket | Exposes the current Clerk session token to the authenticated WebSocket path without persistence; retained. |
| `lib/product/federation/__tests__/store-api.test.ts` | Existing Clerk/WebSocket | Covers authenticated federation stream; retained. |
| `lib/product/federation/state.svelte.ts` | Existing Clerk/WebSocket | Supplies a fresh token to the existing federation socket; retained. |
| `lib/product/socket.ts` | Existing Clerk/WebSocket | Sends a fresh token in the first authenticated frame; URL stays free of credentials. Retained with backend check. |
| `lib/product/state.svelte.ts` | Existing Clerk/WebSocket | Supplies token getter to the existing monitoring socket; retained. |
| `routes/app/federation/live/+page.svelte` | Existing Clerk/WebSocket | Makes disconnected status and manual reconnect visible; retained. |
| `routes/app/history/+page.svelte` | Hardware telemetry | Lists owner-scoped saved hardware sessions alongside simulated sessions; retained. |
| `routes/app/history/[session_id]/+page.svelte` | Hardware telemetry | Shows persisted bounded trace and provenance for hardware session IDs; retained. |
| `routes/app/monitoring/+page.svelte` | Hardware telemetry | Adds source selector and isolated telemetry-only branch; simulated branch is retained. |

Additional files introduced or corrected during final verification: `lib/product/hardware-waveform.ts` and its test bind exact timestamp/ADC plotting and gap breaks; `lib/components/product/ProductShell.svelte` and its existing sidebar test replace a misleading global “simulated only” caption; `routes/app/about/+page.svelte`, `routes/app/device/+page.svelte`, and their copy tests clarify that the Device flow is virtual while Monitor has optional telemetry. These are copy corrections, not route redesigns. No unrelated frontend edit was retained.

The additive `NHM_HARDWARE_MONGO_MONITOR_001` successor binds the complete current frontend file set and hashes of changed non-frontend files. Its `PASS` status means digest and predecessor identity checks pass; its release status is **HOLD** because physical ESP32 verification is unavailable. Seven additive CAP protocol amendments re-pin the Clerk/API/frontend changes; four further amendments re-pin the older tests adjusted to recognize only this exact successor. Historical lock files and frozen scientific artifacts were not edited. `scripts.reconcile_ui_lock_chain` reports zero unauthorized frontend files, and the Studio verifier and all older CAP/UI chains pass with exact-byte successor checks.
