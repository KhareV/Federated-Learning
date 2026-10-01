// Live-update architecture for the NHM dashboard (Section 41). Consumes sequential
// /v1/infer-window outcomes through four explicit entry points so T034 replay can feed the
// same interface without a second, T034-specific dashboard path.
//
// This module holds NO inference/calibration/threshold/episode logic of its own -- it only
// records what the API already decided (Section 18/41).

import type { ErrorResponse, InferWindowRequest, InferWindowResponse, MonitoringState } from '$lib/api/nhm-v1';

export type DashboardOutcome =
	| { kind: 'success'; response: InferWindowResponse }
	| { kind: 'request_error'; status: 400; error: ErrorResponse }
	| { kind: 'signal_window_error'; status: 422; error: ErrorResponse }
	| { kind: 'server_error'; status: 500; error: ErrorResponse }
	| { kind: 'transport_error'; message: string };

export interface HistoryPoint {
	timestamp_us: number | null;
	kind: 'success' | 'gap';
	monitoring_state: MonitoringState | null;
	raw_probability: number | null;
	source_domain_calibrated_probability: number | null;
	threshold: number | null;
	reason: string | null;
}

const HISTORY_LIMIT = 200;

export function createDashboardSession(sessionId: string) {
	let latestOutcome = $state<DashboardOutcome | null>(null);
	let latestEcgWindow = $state<number[] | null>(null);
	let history = $state<HistoryPoint[]>([]);
	let requestCount = $state(0);

	function pushHistory(point: HistoryPoint) {
		history = [...history.slice(-(HISTORY_LIMIT - 1)), point];
	}

	/** A 200 response: the only path that may update the displayed ECG window. */
	function applySuccessfulWindow(request: InferWindowRequest, response: InferWindowResponse): void {
		latestOutcome = { kind: 'success', response };
		latestEcgWindow = request.ecg.samples;
		requestCount += 1;
		pushHistory({
			timestamp_us: response.timestamp_us,
			kind: 'success',
			monitoring_state: response.monitoring_state,
			raw_probability: response.raw_probability,
			source_domain_calibrated_probability: response.source_domain_calibrated_probability,
			threshold: response.threshold,
			reason: null
		});
	}

	/** A 422: unusable/incomplete signal window. MODEL_V1 never ran -- no probability point,
	 * but the backend did accept this as a real window event (Section 27), so it leaves a
	 * gap marker. The displayed ECG window is NOT replaced (nothing new was accepted). */
	function applySignalWindowError(error: ErrorResponse): void {
		latestOutcome = { kind: 'signal_window_error', status: 422, error };
		requestCount += 1;
		pushHistory({
			timestamp_us: null,
			kind: 'gap',
			monitoring_state: 'RECHECK_SENSOR',
			raw_probability: null,
			source_domain_calibrated_probability: null,
			threshold: null,
			reason: error.message
		});
	}

	/** A 400: request/schema contract error. Never reaches ALERT_POLICY_V1 at all -- no
	 * history entry, no fabricated monitoring state (Section 17). */
	function applyRequestError(error: ErrorResponse): void {
		latestOutcome = { kind: 'request_error', status: 400, error };
		requestCount += 1;
	}

	/** A 500: safe generic internal failure. No probability; the previous result must not be
	 * implied to still be current, so this still leaves a gap marker. */
	function applyServerError(error: ErrorResponse): void {
		latestOutcome = { kind: 'server_error', status: 500, error };
		requestCount += 1;
		pushHistory({
			timestamp_us: null,
			kind: 'gap',
			monitoring_state: 'SYSTEM_ERROR',
			raw_probability: null,
			source_domain_calibrated_probability: null,
			threshold: null,
			reason: error.message
		});
	}

	/** Transport/network failure before any HTTP status was obtained. */
	function applyTransportError(message: string): void {
		latestOutcome = { kind: 'transport_error', message };
		requestCount += 1;
	}

	function reset(): void {
		latestOutcome = null;
		latestEcgWindow = null;
		history = [];
		requestCount = 0;
	}

	return {
		sessionId,
		get latestOutcome() {
			return latestOutcome;
		},
		get latestEcgWindow() {
			return latestEcgWindow;
		},
		get history() {
			return history;
		},
		get requestCount() {
			return requestCount;
		},
		applySuccessfulWindow,
		applySignalWindowError,
		applyRequestError,
		applyServerError,
		applyTransportError,
		reset
	};
}

export type DashboardSession = ReturnType<typeof createDashboardSession>;
