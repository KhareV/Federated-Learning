# ruff: noqa: E501
"""NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001: additive presentation/orchestration layer over the two existing federation engines.

Reuses, unchanged: the 3-round product ``FederationService`` (frozen contract), ``fl10.runner.run_training`` (10 rounds, same ``Coordinator`` and
``train_local_epoch_v2``), the FL10 evaluator/metric engine and the frozen FL10 diagnostic holdout. It adds no training engine, no FedAvg and no model;
it observes committed states and publishes run-scoped evaluation records. Nothing here changes a frozen scientific artifact or an accepted lock."""

STUDIO_ID = "NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001"
