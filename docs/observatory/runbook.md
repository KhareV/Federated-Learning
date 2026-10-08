# Local Research Observatory runbook

The Observatory is an additive development successor over Product API V1_3. Its current local verification mode is **explicit offline DEMO**, not connected Clerk. It reads frozen scientific evidence through the existing Research API, but detailed signal traces are deterministic reconstructions of selected synthetic windows, not captured historical arrays.

From the repository root, choose a fresh temporary workspace (outside the repository) and retain its exact path. Start the three services in separate terminals:

```sh
.venv-t032/bin/python -m scripts.run_nhm_default --profile default --host 127.0.0.1 --port 8001
```

```sh
NHM_PRODUCT_AUTH_MODE=DEMO \
NHM_PRODUCT_DEMO_AUTH_ACK=I_UNDERSTAND_THIS_IS_NOT_CLERK \
NHM_PRODUCT_DB_PATH=/absolute/path/to/temporary/product.sqlite3 \
NHM_FEDERATION_ARTIFACT_ROOT=/absolute/path/to/temporary/federation \
NHM_FL_CANDIDATE_ROOT=/absolute/path/to/temporary/candidates \
.venv-t032/bin/python -m scripts.run_observatory_product --host 127.0.0.1 --port 8002
```

```sh
cd frontend
NHM_PRODUCT_API_PORT=8002 npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/sign-in`, enter the visibly labelled offline DEMO workspace, then visit `/app/observatory`, `/app/observatory/federation`, an individual synthetic client view, and `/app/observatory/tour`. The release monitoring path remains on MODEL_V2_FINAL/CAL_V2; the Observatory never promotes a candidate. Do not point the product DB or federation roots at a valuable existing workspace without deliberately choosing to use those records.

For browser verification against this already-running stack:

```sh
.venv-t032/bin/python -m scripts.run_observatory_browser_smoke
```

For connected Clerk TEST evaluation, the additive launcher reuses the accepted Clerk configuration, frontend public-key build, and three-service orchestration while substituting the Observatory API successor. Keep keys in the ignored `.env` file or an external untracked file; never print or commit them:

```sh
.venv-t032/bin/python -m scripts.run_observatory_clerk_connected \
  --env-file .env --inference-port 8011 --product-port 8012 \
  --frontend-port 5183 --build
```

The accepted legacy launcher’s current-tree UI preflight rejects Observatory frontend changes bound by the historical UI lock. The additive launcher discloses that expected successor mismatch, verifies the accepted V1_9 files at the entry commit and the unchanged protected surfaces, then runs the other applicable preflights. It does not alter old locks. Open `http://127.0.0.1:5183/sign-in`. The authenticated two-user journey is automated by `scripts.run_observatory_clerk_e2e --env-file <env> --users-file <json outside Git> --out <dir>` (real Chrome, real Clerk TEST sign-in; evidence holds booleans, statuses, counts and digests only). Do not substitute DemoAuth results.
