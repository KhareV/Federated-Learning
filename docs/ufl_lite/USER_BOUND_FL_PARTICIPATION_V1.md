# USER_BOUND_FL_PARTICIPATION_V1 — design note (UFL-LITE-001)

## What this is
For a signed-in Clerk user's own LIVE_RUN, the existing federated client **SIM_FL_SITE_00** is *presented* as that user's edge client ("MY EDGE CLIENT") and SIM_FL_SITE_01..07 as synthetic peers. This is a presentation role only. Nothing about training, aggregation or the model changes.

## Why slot 00 and not a ninth client
A ninth client would change aggregation weights, the update count (24), the candidate digest, the cohort assumptions, the frozen engineering evidence, the tests, the SecAgg expectations and demo reproducibility. Reusing an existing slot keeps the federation mathematically identical: the canonical candidate digest `3f0b7762ae7e05f21eb1709521404ed4d7968cae34f89e1797a0cbabd47c70e4` (8 clients, 3 rounds, FedAvg + SecAgg shadow) must be reproduced exactly. The Clerk user is never hashed into a client, and no client id is renamed.

## What "MY EDGE CLIENT" means
The authenticated user owns the run and may view/control it; for that run the product labels SIM_FL_SITE_00 as the user's edge participation client. Identity is used only for ownership, authorization and this label.

## What stays synthetic and what trains
SIM_FL_SITE_00 still trains on its existing private synthetic engineering dataset (93 examples, dataset sha `fca44709…bd25e2` frozen in the baseline) through the existing `LocalTrainingBufferV1` and `CapstoneFlClientAdapterV2`, with existing simulation-truth labels. `data_origin` remains SYNTHETIC_ENGINEERING. The dataset is an engineering fixture attached to the slot; it does not represent the user's physiology. The user's monitoring history (inference events, heart rate, SpO2 context, quality, state events, waveform previews) is never copied into a training buffer: monitoring sessions and FL training buffers are separate, and there is no "train from my session" action. No model prediction is used as a label.

## Why the global candidate is unchanged
Identity never reaches a CNN input, optimizer, label, tensor, loss, aggregation weight, model state, update digest or candidate digest. The binding is a function of (backend auth provider, run type, client id) evaluated at presentation time. The candidate remains ACCEPTED_TO_SANDBOX, IN_SANDBOX, production_deployed=false.

## Why this is not personalized FL
There is one global candidate and no personal model, per-user checkpoint, per-user threshold or fine-tuning. The preferred name is USER_BOUND_FL_PARTICIPATION (identity-bound participation). Allowed statement: "One existing federated edge client is bound to the authenticated user for the demonstration. It performs genuine local training on its private synthetic labelled dataset, while seven synthetic peers participate in the same live federation."

## Where the binding applies
- CLERK mode and LIVE_RUN only. `GET /federation/clients` is a global cohort view (no user, no run) and must not show a user binding.
- DEMO mode: no binding, so the offline CAP-010/CAP-011 demo is preserved exactly.
- REPLAY: no owner binding; a replay is shown as historical engineering replay and the binding never alters replay events or digests.
- FedAvg and FedProx are treated identically; SecAgg is unchanged and adds no privacy claim.

## Derived, not persisted
The role is derived at presentation time (no schema, API field or artifact metadata). `FLClientIdentity` and `FederationRun` are frozen `extra="forbid"` contracts, so a serialised field would force contract and API amendments; the derived rule is restart-correct because it depends only on the persisted run owner and run type and the backend auth mode.

## Phase-2 insertion points (not implemented here)
A small pure helper for the role, an optional `ClientGrid` prop and its wiring on the federation live/rounds pages, plus tests. No backend, FL, buffer, coordinator, database or Clerk change is expected. Note: any frontend edit needs a new UI successor lock and generalising the successor-aware UI verifiers.

## Future seam (not implemented)
The existing `LocalTrainingBufferV1` interface could later be fed by a validated real-labelled local source. This is neither designed nor implemented in UFL-LITE, and involves no hardware, BLE or label acquisition.
