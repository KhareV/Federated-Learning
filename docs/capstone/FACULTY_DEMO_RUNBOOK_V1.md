# FACULTY DEMO RUNBOOK V1 (CAPSTONE_DEMO_RUNBOOK_V1)

Offline, one-laptop demonstration of the NHM capstone product. **Engineering demonstration of a research prototype - not diagnostic, not clinical, not deployed.**

## 1. Setup assumptions

* The locked Python environment and the frontend dependencies are already installed (the launcher never installs packages): `pip check` is clean, `frontend/node_modules` and `frontend/clerk-sdk/node_modules` exist.
* No network is needed; the demo uses an OFFLINE DEMO identity (not Clerk). The browser needs only `127.0.0.1`.
* **SIMULATION TIMING: ACCELERATED FOR PRESENTATION.** This changes pacing only - source samples, event order, model inputs, quality, model outputs and FL computations are unchanged. It is not "real-time".

## 2. Launch (one command)

```
python -m scripts.run_capstone_faculty_demo --acknowledge-demo-auth --build --prewarm-federation
```

* Without `--acknowledge-demo-auth` the launcher refuses to start. `--build` rebuilds the existing frontend once; omit it when the build is current.
* The launcher runs a preflight (identities and artifacts only - no training, inference, bootstrap, calibration, FL or SecAgg), starts exactly three services (released inference `SOFTWARE_SYSTEM_V2 / MODEL_V2_FINAL` on 8001, product backend `CAPSTONE_PRODUCT_API_V1_3` on 8002, production frontend build on 4173) and prints `NHM FACULTY DEMO READY` only after all three answer their readiness probes.
* `--prewarm-federation` performs one read (`GET /federation/clients`): *PREPARING 8 SYNTHETIC FEDERATED CLIENT DATASETS*, several seconds, machine-specific. It trains nothing and creates no run or candidate.
* Runtime data lives in an isolated workspace outside the Git tree (printed at startup). `--mode resume --workspace <dir>` reopens a previous demo workspace; `--reset --workspace <dir>` deletes only a validated demo workspace. Rollback profiles are not part of the faculty demo.
* Open `http://127.0.0.1:4173/sign-in`.

## 3. SHORT PATH (about 5-7 minutes, planning range only)

1. **Sign in** through OFFLINE DEMO. *Say:* "This is an offline demo identity, not a real account."
2. **Overview.** *Say:* "Released monitoring uses MODEL_V2_FINAL; federated development is a separate lane and never changes it."
3. **Device** -> attach the virtual wearable `MIXED_MONITORING_SESSION` -> **Scan** -> **Connect**. *Say:* "The device is simulated. It enters through the same DeviceSource boundary intended for future physical hardware."
4. **Monitor** -> create session -> start. Watch the live stream until the session completes. *Say:* "The simulated record enters the unchanged signal-processing runtime and the released MODEL_V2_FINAL research monitor. PPG and SpO2 are context, not ECG-classifier inputs. This is a non-diagnostic research monitor." Whatever the model honestly outputs is what is shown; nothing is tuned.
5. **History** -> open the session: persisted summary, separate source/product-clock timelines, bounded ECG preview (not raw storage).
6. **Federation** -> LIVE_RUN, FEDAVG, SECAGG_SHADOW -> create and start. *Say:* "These eight clients are synthetic research partitions running logically on one laptop. Each performs genuine local optimization. The server receives model updates rather than local training examples. The SecAgg+ demonstration is a round-1 protected-aggregation shadow; authoritative aggregation remains plain." Watch 3 rounds, the shadow, completion.
7. **Models.** *Say:* "The final global state becomes one engineering candidate. Passing structural governance admits it to the sandbox registry only. It is never automatically deployed, and MODEL_V2_FINAL is still the released default."
8. **Research -> ML and FL.** *Say:* "The historical model promotion decision `MODEL_V2_NOT_PROMOTED_RELEASE_CI` and the later software-release decision `SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED` are different questions; the later acceptance does not retroactively pass the earlier test."
9. **System.** The product reports hardware mode SIMULATED_ONLY and no physical hardware.

## 4. FULL PATH (about 10-15 minutes, planning range only)

Add, without running any new science: the four monitoring scenarios (normal, context loss, poor signal, disconnect/reconnect) and how the mixed session combines them; the distinctions between source time, product clock and persisted-window counts on the History page; FedAvg versus the frozen FedProx configuration (FedProx transfer was mixed and is not claimed as better); the SecAgg shadow scope; REPLAY (optional, only after a completed compatible live run - the UI says NO TRAINING IS EXECUTING and it creates no candidate, no governance decision and no training); the five structural candidate checks; research-evidence provenance and negative findings; and the physical-device replacement boundary.

## 5. Answers to likely questions

* **Does it train a personal model for the user?** No. The logged-in user's monitoring session uses the released common MODEL_V2_FINAL. The federation demo uses separate synthetic research clients. User monitoring sessions are not added to FL. There is no personal model and no continuous learning.
* **Is real hardware connected?** No. Physical wearable integration is not done yet; it is the next source-adapter step. The software is designed around the DeviceSource / ObservedRecord boundary; BLE format, source rate, scaling, clock drift, real labels and physical sensor characteristics remain VERIFICATION_REQUIRED.
* **Are the eight clients hospitals or separate machines?** No: eight logical synthetic partitions on one laptop. The "one live run at a time" rule is a one-laptop policy, not a distributed lock.
* **Is the federation private?** The coordinator receives model updates, not local training examples. The SecAgg+ shadow covers round 1 only (a protected-aggregation interface); it is not differential privacy and gives no anonymity guarantee.
* **Was the candidate deployed or evaluated?** No. It is an engineering sandbox entry; no candidate inference runtime exists and no accuracy is computed.

## 6. Known wait points

First federation page load (client dataset preparation, several seconds, skipped if prewarmed); the federation run (genuine training, machine-specific); frontend build when `--build` is used. These durations are observations, not requirements.

## 7. Failure and recovery

* **Inference service fails:** stop the stack and read `<workspace>/logs/inference.log`.
* **Product API fails:** stop the stack and read `product.log`. **Frontend fails:** read `frontend.log`.
* **Port occupied:** the launcher reports `PORT_IN_USE:<service>:<port>` and does not touch the occupant; choose `--inference-port/--product-port/--frontend-port` or stop the known local process yourself. Never kill arbitrary processes.
* **A monitoring session fails:** do not fake completion; show the FAILED state and create a NEW session. **A federation run fails:** keep it as FAILED engineering evidence and create a NEW LIVE_RUN.
* **Fallback:** persisted history or REPLAY may be shown only if clearly labelled historical. Never present static charts as live execution.

## 8. Shutdown

Press Ctrl+C in the launcher terminal: the frontend, product backend and inference service are stopped in that order and only the processes the launcher started are signalled. Logs stay in the workspace.

## 9. Claim boundary

This is a demonstration of a research prototype using simulated device input, released research monitoring, genuine engineering federation, persistent history and frozen research-evidence views. It is not a clinical, diagnostic or production system, not a clean-machine release (that is a later phase) and not physical-wearable validation.
