# CAPSTONE_UI_V1 (CAP-005)

The existing SvelteKit app in `frontend/` extended into the capstone product interface. It supersedes
`DASHBOARD_UI_V1_5` (whose lock file is preserved byte-identical) and is bound by
`artifacts/capstone/CAPSTONE_UI_V1.lock.json`.

## Run (offline DEMO)
```
python -m scripts.run_nhm_default                      # SOFTWARE_SYSTEM_V2 on :8001
NHM_PRODUCT_AUTH_MODE=DEMO NHM_PRODUCT_DEMO_AUTH_ACK=I_UNDERSTAND_THIS_IS_NOT_CLERK \
  python -m scripts.run_capstone_product               # product API on :8002 (SQLite)
cd frontend && npm ci && npm ci --prefix clerk-sdk && npm run dev
```
Open `/` -> **OPEN NHM** -> `/sign-in` -> **ENTER DEMO WORKSPACE** -> `/app`. `NHM_PRODUCT_API_PORT`
overrides the product proxy port; `/v1` (research runtime) is unchanged.

## Clerk (CLERK mode only)
The backend `/product/v1/system` decides the mode. In CLERK mode the official `@clerk/clerk-js` (exact pin
6.37.0, additive package `frontend/clerk-sdk`, because the frozen V2-014 lock binds `frontend/package.json`)
is imported lazily and `VITE_CLERK_PUBLISHABLE_KEY` (public, browser-safe) is required. REST calls send
`Authorization: Bearer <session token>` (never stored); the monitoring WebSocket is same-origin and relies
on the Clerk session cookie. There is no fallback to Demo. Secrets are never placed in the frontend.

## Layers
`lib/product/types.ts` (contracts) - `events.ts` (strict PRODUCT_LIVE_EVENT_V1 parser + sequence) -
`waveform.ts` (bounded rolling buffer, null gaps) - `live-model.ts` (pure reducer) - `socket.ts` (bounded
reconnect) - `api.ts` (typed client) - `auth.ts` (CAPSTONE_FRONTEND_AUTH_V1) - `state.svelte.ts` (store) -
`routes/sign-in`, `routes/app/*` (shell, device, monitoring, history, not-yet-enabled future shells).

Scope boundary: no FL runtime, no candidates, no session analytics (CAP-009), no hardware.
