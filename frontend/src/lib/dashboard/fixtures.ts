// UI_TEST_FIXTURE -- deterministic fixtures for the dashboard test suite only.
//
// These are NOT scientific evidence and must never be imported by production dashboard code
// (routes/ or any non-test component). They exist solely so the five canonical monitoring
// states, the 400/422/500 HTTP paths, and context-availability/quality-warning variants can be
// exercised without hardware or a running backend. Shapes are derived from the real
// API_SCHEMA_V1 response/error shape (contracts/API_SCHEMA_V1.json) -- no alternate
// dashboard-only schema is introduced.

import type { ErrorResponse, InferWindowResponse, MonitoringState } from '$lib/api/nhm-v1';

export const UI_TEST_FIXTURE = 'UI_TEST_FIXTURE' as const;

const BASE_RESPONSE: Omit<InferWindowResponse, 'monitoring_state' | 'context' | 'ecg_quality'> = {
	contract_version: 'API_SCHEMA_V1',
	timestamp_us: 1_000_000,
	model_id: 'MODEL_V1',
	target: 'AAMI_SVF_WINDOW_V1',
	raw_probability: 0.52,
	source_domain_calibrated_probability: 0.58,
	calibration_domain: 'MIT-BIH-v1.0.0',
	calibration_patient_count: 3,
	calibration_id: 'CAL_V1',
	threshold: 0.61,
	latency_ms: 4.2,
	preprocess_version: 'PREPROC_V1',
	alert_policy_id: 'ALERT_POLICY_V1'
};

const BASE_CONTEXT = {
	ppg_quality: 'VALID' as const,
	pr_ppg_bpm: 71.5,
	spo2_pct: 97.8,
	spo2_valid: true,
	hr_ecg_bpm: 72.1,
	context_available: true,
	quality_warning: false,
	quality_warning_reasons: [] as string[],
	possible_pattern: false,
	ecg_hr_context_id: 'ECG_HR_CONTEXT_V2'
};

function response(
	monitoring_state: MonitoringState,
	overrides: Partial<InferWindowResponse> = {},
	contextOverrides: Partial<typeof BASE_CONTEXT> | null = BASE_CONTEXT
): InferWindowResponse {
	return {
		...BASE_RESPONSE,
		ecg_quality: 'VALID',
		monitoring_state,
		context: contextOverrides ? { ...BASE_CONTEXT, ...contextOverrides } : null,
		...overrides
	};
}

export const FIXTURE_NORMAL_MONITORED_PATTERN: InferWindowResponse = response(
	'NORMAL_MONITORED_PATTERN',
	{ source_domain_calibrated_probability: 0.31 }
);

export const FIXTURE_POTENTIAL_ECTOPY_ASSOCIATED_PATTERN: InferWindowResponse = response(
	'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN',
	{ source_domain_calibrated_probability: 0.74 },
	{ ...BASE_CONTEXT, possible_pattern: false }
);

export const FIXTURE_RECHECK_SENSOR_DEGRADED: InferWindowResponse = response(
	'RECHECK_SENSOR',
	{ ecg_quality: 'DEGRADED', source_domain_calibrated_probability: 0.69 },
	{ ...BASE_CONTEXT, possible_pattern: true }
);

export const FIXTURE_CONTEXT_UNAVAILABLE: InferWindowResponse = response(
	'CONTEXT_UNAVAILABLE',
	{ source_domain_calibrated_probability: 0.22 },
	null
);

export const FIXTURE_SYSTEM_ERROR: InferWindowResponse = response('SYSTEM_ERROR', {
	raw_probability: null,
	source_domain_calibrated_probability: null,
	model_id: null,
	calibration_domain: null,
	calibration_patient_count: null,
	calibration_id: null,
	threshold: null,
	preprocess_version: null,
	alert_policy_id: null
});

export const FIXTURE_QUALITY_WARNING: InferWindowResponse = response(
	'NORMAL_MONITORED_PATTERN',
	{ source_domain_calibrated_probability: 0.3 },
	{
		...BASE_CONTEXT,
		hr_ecg_bpm: 110,
		pr_ppg_bpm: 72,
		quality_warning: true,
		quality_warning_reasons: ['HR_PPG_DISAGREEMENT_SUSTAINED']
	}
);

export const FIXTURE_ERROR_400: ErrorResponse = {
	contract_version: 'API_SCHEMA_V1',
	status_code: 400,
	error_type: 'REQUEST_SCHEMA_ERROR',
	message: 'body.ecg.samples: Value error, NONFINITE_VALUE:ecg.samples'
};

export const FIXTURE_ERROR_422: ErrorResponse = {
	contract_version: 'API_SCHEMA_V1',
	status_code: 422,
	error_type: 'UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW',
	message: 'INCOMPLETE_SIGNAL_WINDOW: 2499 samples, ecg_quality=VALID'
};

export const FIXTURE_ERROR_500: ErrorResponse = {
	contract_version: 'API_SCHEMA_V1',
	status_code: 500,
	error_type: 'INTERNAL_SERVER_ERROR',
	message: 'An internal server error occurred. The window may be retried.'
};

export const ALL_STATE_FIXTURES: Record<MonitoringState, InferWindowResponse> = {
	NORMAL_MONITORED_PATTERN: FIXTURE_NORMAL_MONITORED_PATTERN,
	POTENTIAL_ECTOPY_ASSOCIATED_PATTERN: FIXTURE_POTENTIAL_ECTOPY_ASSOCIATED_PATTERN,
	RECHECK_SENSOR: FIXTURE_RECHECK_SENSOR_DEGRADED,
	CONTEXT_UNAVAILABLE: FIXTURE_CONTEXT_UNAVAILABLE,
	SYSTEM_ERROR: FIXTURE_SYSTEM_ERROR
};
