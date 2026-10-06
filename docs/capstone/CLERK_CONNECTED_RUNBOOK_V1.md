# CAPSTONE_CLERK_CONNECTED_V1 — Connected Clerk Runbook

## 1. Two intentionally separate modes

- **OFFLINE DEMO (DemoAuth).** The historical faculty mode: explicit DemoAuth acknowledgement, no Clerk initialisation, loopback-only runtime. Command: `python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth ...` (unchanged).
- **CONNECTED CLERK.** Real Clerk TEST-instance authentication. It requires Internet access to Clerk-owned origins, so it is not an offline mode and does not claim to be one.

The mode is a launch-time system configuration. There is no browser-side switch, and Clerk mode never falls back to DemoAuth: if Clerk cannot initialise the page shows AUTHENTICATION UNAVAILABLE.

## 2. Environment variables

Credentials come from the environment only (or an explicit `--env-file` that lives outside Git). Never put them in a tracked file, in documentation, in the frontend source or in a command line.

- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (or the Vite-native `VITE_CLERK_PUBLISHABLE_KEY`): the browser-safe publishable key. The launcher maps it to `VITE_CLERK_PUBLISHABLE_KEY` for the Vite build and preview; the frontend never reads `NEXT_PUBLIC_*`.
- `CLERK_SECRET_KEY`: server-only. It is passed to the product API process only, never to the frontend build or preview.
- `NHM_CLERK_AUTHORIZED_PARTIES`: explicit frontend origin(s). Default `http://127.0.0.1:4173`. A wildcard is refused.

The launcher refuses to start when a key is missing, is not a `pk_test_` / `sk_test_` key, or the authorized parties are not explicit origins.

## 3. Launch

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=<pk_test_...> CLERK_SECRET_KEY=<sk_test_...> python -m scripts.run_capstone_clerk_connected --build --workspace <WORKSPACE_OUTSIDE_REPO>
```

It starts exactly the three services of the faculty stack (inference 8001, product API 8002, frontend 4173) and prints READY only after all three are ready. Stop with Ctrl+C. The product reports `auth_provider = CLERK` and `demo_mode = false` at `/product/v1/system`.

## 4. Sign in, use, sign out

1. Open `http://127.0.0.1:4173/sign-in` and sign in with a Clerk TEST user. In a development instance a new browser may ask for Clerk's documented test verification code for `+clerk_test` addresses.
2. The app calls the product API with `Authorization: Bearer <session token>` obtained from the active Clerk session on every request. The token is never stored by NHM.
3. Monitoring and federation live streams are same-origin browser WebSockets that carry the Clerk session cookie; no token appears in a WebSocket URL. Unauthenticated sockets close with 4401, another user's resource with 4403.
4. Device, monitoring, history, federation, models and research pages behave exactly as in the offline mode. The released monitoring model is still the common MODEL_V2_FINAL. No personal model is trained, and a user's session history does not feed federation.
5. Sign out clears the identity; protected REST then returns 401 and protected sockets close with 4401.

## 5. Ownership

Every owner-scoped resource (devices, sessions, summaries, timelines, federation runs, candidates) belongs to the signed-in Clerk user. Another user receives 403 over REST and 4403 over WebSocket. Global research and model views stay readable.

## 6. Limitations

- Clerk uses TEST credentials on a development instance. This verifies integration behaviour, not production-account operation.
- The connected mode needs network access to Clerk. The offline DemoAuth mode needs none.
- There is no production Clerk deployment claim, no security certification, no penetration test and no compliance claim.
- All capstone limitations are inherited: non-diagnostic research prototype, simulated device only, accelerated timing, logical one-laptop federation clients, SecAgg round-1 shadow only, candidate sandbox only and never automatically deployed.
