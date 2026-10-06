# CAPSTONE_RELEASE_V1 — Release Guide

## 1. What this release is

CAPSTONE_RELEASE_V1 is a clean-clone reproducible, one-laptop research-software/faculty-demonstration release of the NHM capstone product using simulated device input, released MODEL_V2_FINAL monitoring, genuine engineering federation, persistent history, and frozen research-evidence views.

The release claim does not include physical wearable validation, clinical use, medical-device status, production deployment, security certification, hospital deployment, differential privacy, anonymous federation, or clean-room raw-dataset scientific reproduction.

The release is the exact Git repository state at the RELEASE_TARGET_SHA recorded in `reports/capstone/cap_011/release_target.json` and in the final handoff. There is no installer and no source archive. This release is not the historical project-level RELEASE_V1 and does not complete or modify it.

## 2. Network: installation versus runtime

Initial dependency installation may require Internet access to the public Python and npm package registries. No air-gapped installation is claimed and no dependency is vendored.

After the dependencies are installed, the canonical DEMO product runtime requires only loopback networking. It was verified with all non-loopback browser requests blocked, and ClerkJS is not initialised in DemoAuth mode.

## 3. Raw-data and re-execution boundary

The repository contains frozen scientific artifacts and evidence, but CAPSTONE_RELEASE_V1 does not claim full raw-data retraining/evaluation from a clean clone. The clean-clone claim is software, artifact and product-demonstration reproducibility only.

No raw biomedical dataset download is required to operate the capstone demonstration. The MIT-BIH, INCART, NSTDB and BIDMC raw datasets belong to historical scientific reproducibility and are not needed here; they must not be copied into a clean clone. The demonstration uses tracked frozen model artifacts, tracked synthetic simulation machinery and tracked research summary evidence.

Tests that need untracked raw data are skipped by the repository's existing CLEAN_CLONE_GATING_V1 and are reported as data-gated skips; they are never forced to pass.

## 4. Prerequisites

- Python 3.11 available as `python3.11`.
- Node.js and npm (the tested versions are recorded in the clean-clone environment inventory).
- Git, with access to the remote repository.
- Google Chrome, only to run the automated browser verification of the demo.
- Tested platform: macOS (Darwin) on arm64 with the toolchain recorded in the clean-clone environment inventory. Other operating systems are not verified and no cross-platform claim is made.

## 5. Get the exact release target

Clone the remote repository and check out the exact release target commit. A branch name alone is not accepted; use the full 40-character SHA.

```bash
git clone <REMOTE_URL> nhm-capstone
git -C nhm-capstone checkout --detach <RELEASE_TARGET_SHA>
cd nhm-capstone
export PYTHONPATH=src:.
```

## 6. Python environment (locked installation)

Create a new virtual environment inside the clone (it is git-ignored) and install only from the committed lock files. Never reuse another checkout's environment.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -r requirements-capstone-auth.lock
.venv/bin/python -m pip check
```

## 7. Frontend installation (locked)

Install the separately locked ClerkJS package and the frontend from their committed lock files. Do not copy `node_modules` or a frontend build from anywhere.

```bash
npm ci --prefix frontend/clerk-sdk
npm ci --prefix frontend
```

## 8. Verify the release

The release verifier checks all capstone locks and amendment chains, the release policy, protocol and manifest, and the protected artifact hashes. It performs no training, inference, federated learning or scientific calculation.

```bash
.venv/bin/python -m scripts.verify_capstone_release_v1
.venv/bin/python -m pytest tests/test_capstone_release_lib.py tests/test_capstone_release_harness.py tests/test_capstone_release_guide.py tests/test_capstone_release_target.py -q -rA -p no:cacheprovider
.venv/bin/python -m pytest tests -q -p no:cacheprovider --deselect tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers
.venv/bin/python -m pytest tests/test_capstone_monitoring_websocket.py::test_monitoring_completes_with_zero_subscribers -q -p no:cacheprovider
npm test --prefix frontend
npm run check --prefix frontend
npm run build --prefix frontend
```

The one deselected test is the inherited CAP-003 timing race. It is run separately in isolation (up to five attempts) and is accepted only if it passes once and every failed attempt carries the known signature `AssertionError: assert (789 > 100 and False)`. The frozen test is not repaired.

## 9. Faculty demonstration

Run the preflight first. It verifies identities and artifacts only and executes no science. The `--build` flag tells it that the launcher will build the frontend itself (the launcher writes the build stamp that a later preflight checks), so the production build is not required to exist yet.

```bash
.venv/bin/python -m scripts.run_capstone_faculty_demo --preflight-only --acknowledge-demo-auth --build
```

Launch the faculty stack with the single governed launcher. The workspace is created outside the repository; the launcher manages exactly three services (inference on 8001, product API on 8002, frontend on 4173), prints READY only after all three are ready, and stops them in reverse order on Ctrl+C.

```bash
.venv/bin/python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth --build --prewarm-federation --workspace <WORKSPACE_OUTSIDE_REPO>
```

The faculty walkthrough is `docs/capstone/FACULTY_DEMO_RUNBOOK_V1.md`. To reproduce the complete automated real-browser journey, including a stop and resume of the same workspace, set an empty evidence directory outside the repository and run:

```bash
export CAP010_OUT=<EMPTY_DIRECTORY_OUTSIDE_REPO>
.venv/bin/python -m scripts.run_capstone_full_demo_e2e run 1 --restart
```

## 10. What the demo shows, and what it does not

- Monitoring uses the common released MODEL_V2_FINAL (SOFTWARE_SYSTEM_V2, CAL_V2). No personal model is trained, and user session history does not feed federation.
- Federation uses eight synthetic logical clients on one laptop (three rounds, 24 genuine updates, authoritative aggregation PLAIN with a round-1 SecAgg shadow).
- One engineering candidate is created in the demo workspace. It is ACCEPTED_TO_SANDBOX, IN_SANDBOX and production_deployed=false; it is never automatically deployed and it is not used for monitoring.
- Hardware mode is SIMULATED_ONLY and physical_hardware_available is false. Future physical hardware remains VERIFICATION_REQUIRED.
- The historical decisions are preserved unchanged: MODEL_V2_NOT_PROMOTED_RELEASE_CI (model promotion) and SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED (software system). The release decision answers a third question: whether the finished capstone package is clean-clone reproducible and faculty-ready.
- This release is not security audited, not penetration tested, not HIPAA compliant, not privacy certified and not production hardened.

## 11. Known limitations

- non-diagnostic research prototype
- physical wearable absent
- WEARABLE_V1 validation absent
- simulation-only device path
- accelerated demo timing
- MODEL_V2 historical release-seed promotion CI crossed zero
- only six eligible INTERNAL_TEST groups
- CAL_V2 source-domain only
- V2-010 / INCART second-look caveats
- QUALITY_V1 stuck-nonzero limitation
- SecAgg narrow protected-aggregation-interface claim
- no differential privacy
- logical one-laptop FL clients
- candidate sandbox has no inference runtime
- candidate not deployed
- Clerk real-account WebSocket path not verified
- one-active-FL-run is not distributed locking
- CAP-003 inherited timing race
- npm dependency advisories already disclosed
- installation may need public package-registry network access
- clean release is not raw-data scientific re-execution

## 12. Troubleshooting

If a port is occupied the launcher reports PORT_IN_USE and never touches the other process. If a clean clone fails for any reason, do not copy files into it: discard it and create a new clone. Timings printed by the tools are machine-specific telemetry, not requirements.
