// Typed client for the frozen NHM research-runtime HTTP API (T032, API_RUNTIME_V1).
//
// Binds ONLY to POST /v1/infer-window as defined by contracts/API_SCHEMA_V1.json and
// contracts/openapi_v1.json. This module does not reimplement MODEL_V1, CAL_V1, threshold
// comparison, K=2/M=2 debouncing, cooldown, fusion, or HR-disagreement logic -- the API
// response is authoritative. Field names below mirror api/schemas.py exactly; no aliases are
// invented where unnecessary.

export const CONTRACT_VERSION = 'API_SCHEMA_V1' as const;
export const TARGET_ID = 'AAMI_SVF_WINDOW_V1' as const;
export const ECG_WINDOW_TARGET_HZ = 250 as const;
export const ECG_WINDOW_SECONDS = 10 as const;
export const ECG_WINDOW_SAMPLE_COUNT = ECG_WINDOW_TARGET_HZ * ECG_WINDOW_SECONDS;

/** Exactly the five canonical monitoring states -- see fusion/state_machine.py. */
export const MONITORING_STATES = [
	'NORMAL_MONITORED_PATTERN',
	'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN',
	'RECHECK_SENSOR',
	'CONTEXT_UNAVAILABLE',
	'SYSTEM_ERROR'
] as const;
export type MonitoringState = (typeof MONITORING_STATES)[number];

export const QUALITY_STATES = ['VALID', 'DEGRADED', 'UNUSABLE'] as const;
export type QualityState = (typeof QUALITY_STATES)[number];

export interface ECGWindow {
	samples: number[];
	target_hz: typeof ECG_WINDOW_TARGET_HZ;
	window_seconds: typeof ECG_WINDOW_SECONDS;
}

export interface PPGContext {
	quality: QualityState | null;
	pr_bpm: number | null;
	spo2_pct: number | null;
	spo2_valid: boolean | null;
}

export interface InferWindowRequest {
	contract_version: typeof CONTRACT_VERSION;
	session_id: string;
	timestamp_us: number;
	ecg: ECGWindow;
	ecg_quality: QualityState;
	ppg_context: PPGContext | null;
	model_id: string;
}

export interface InferWindowContext {
	ppg_quality: QualityState | null;
	pr_ppg_bpm: number | null;
	spo2_pct: number | null;
	spo2_valid: boolean;
	hr_ecg_bpm: number | null;
	context_available: boolean;
	quality_warning: boolean;
	quality_warning_reasons: string[];
	possible_pattern: boolean;
	ecg_hr_context_id: string;
}

/** Mirrors api/schemas.py::InferWindowResponse exactly. */
export interface InferWindowResponse {
	contract_version: typeof CONTRACT_VERSION;
	timestamp_us: number;
	model_id: string | null;
	target: typeof TARGET_ID;
	raw_probability: number | null;
	source_domain_calibrated_probability: number | null;
	calibration_domain: string | null;
	calibration_patient_count: number | null;
	calibration_id: string | null;
	threshold: number | null;
	ecg_quality: QualityState;
	monitoring_state: MonitoringState;
	context: InferWindowContext | null;
	latency_ms: number | null;
	preprocess_version: string | null;
	alert_policy_id: string | null;
}

/** Mirrors api/schemas.py::ErrorResponse exactly. status_code is always 400, 422, or 500. */
export interface ErrorResponse {
	contract_version: typeof CONTRACT_VERSION;
	status_code: 400 | 422 | 500;
	error_type: string;
	message: string;
}

export type InferWindowResult =
	| { kind: 'success'; status: 200; data: InferWindowResponse }
	| { kind: 'request_error'; status: 400; error: ErrorResponse }
	| { kind: 'signal_window_error'; status: 422; error: ErrorResponse }
	| { kind: 'server_error'; status: 500; error: ErrorResponse }
	| { kind: 'transport_error'; status: null; message: string };

export interface NhmApiClientOptions {
	/** Same-origin by default (empty string): the real deployment proxies /v1 to the FastAPI
	 * service. Override only for a non-same-origin research setup. */
	baseUrl?: string;
	fetchImpl?: typeof fetch;
}

const DEFAULT_BASE_URL =
	(typeof import.meta !== 'undefined' &&
		(import.meta as unknown as { env?: Record<string, string> }).env?.VITE_NHM_API_BASE_URL) ||
	'';

const ROUTE_PATH = '/v1/infer-window';

export function createNhmApiClient(options: NhmApiClientOptions = {}) {
	const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL;
	const fetchImpl = options.fetchImpl ?? fetch;

	async function inferWindow(request: InferWindowRequest): Promise<InferWindowResult> {
		let response: Response;
		try {
			response = await fetchImpl(`${baseUrl}${ROUTE_PATH}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(request)
			});
		} catch (cause) {
			return {
				kind: 'transport_error',
				status: null,
				message: cause instanceof Error ? cause.message : 'Network request failed.'
			};
		}

		let body: unknown;
		try {
			body = await response.json();
		} catch {
			return {
				kind: 'transport_error',
				status: null,
				message: `Response was not valid JSON (HTTP ${response.status}).`
			};
		}

		if (response.status === 200) {
			return { kind: 'success', status: 200, data: body as InferWindowResponse };
		}
		if (response.status === 400) {
			return { kind: 'request_error', status: 400, error: body as ErrorResponse };
		}
		if (response.status === 422) {
			return { kind: 'signal_window_error', status: 422, error: body as ErrorResponse };
		}
		if (response.status === 500) {
			return { kind: 'server_error', status: 500, error: body as ErrorResponse };
		}
		return {
			kind: 'transport_error',
			status: null,
			message: `Unexpected HTTP status ${response.status}.`
		};
	}

	return { inferWindow };
}

export type NhmApiClient = ReturnType<typeof createNhmApiClient>;

export const nhmApi = createNhmApiClient();
