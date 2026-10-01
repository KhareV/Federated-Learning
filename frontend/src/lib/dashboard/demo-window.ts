// Production placeholder window source -- NOT a test fixture, NOT SimulationTruth.
//
// WEARABLE_V1 is unavailable and T034 (replay/live end-to-end integration) has not started, so
// there is currently no real signal source to feed the dashboard. Until then, this module
// provides the minimal deterministic 10-second window the dashboard needs to demonstrate a
// genuine, end-to-end call into the real POST /v1/infer-window endpoint -- every probability,
// monitoring_state, and context value the dashboard displays for it is computed by the real
// backend (MODEL_V1/CAL_V1/ALERT_POLICY_V1), never by this module.
//
// This is explicitly NOT a claim of live sensor data -- the dashboard labels it accordingly.

import { ECG_WINDOW_SAMPLE_COUNT } from '$lib/api/nhm-v1';

/** A flat (silent-lead) window: deterministic, previously verified against the real gateway
 * during T032 integration testing. Not physiological data. */
export function flatDemoWindow(): number[] {
	return new Array(ECG_WINDOW_SAMPLE_COUNT).fill(0);
}
