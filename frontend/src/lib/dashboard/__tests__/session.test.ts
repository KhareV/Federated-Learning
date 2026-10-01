import { describe, expect, it } from 'vitest';
import type { ErrorResponse, InferWindowRequest, InferWindowResponse } from '$lib/api/nhm-v1';
import { createDashboardSession } from '../session.svelte';

function request(timestamp_us: number): InferWindowRequest {
	return {
		contract_version: 'API_SCHEMA_V1',
		session_id: 'sess-1',
		timestamp_us,
		ecg: { samples: [0.1, 0.2, 0.3], target_hz: 250, window_seconds: 10 },
		ecg_quality: 'VALID',
		ppg_context: null,
		model_id: 'MODEL_V1'
	};
}

function response(overrides: Partial<InferWindowResponse> = {}): InferWindowResponse {
	return {
		contract_version: 'API_SCHEMA_V1',
		timestamp_us: 1_000_000,
		model_id: 'MODEL_V1',
		target: 'AAMI_SVF_WINDOW_V1',
		raw_probability: 0.9,
		source_domain_calibrated_probability: 0.95,
		calibration_domain: 'MIT-BIH-v1.0.0',
		calibration_patient_count: 3,
		calibration_id: 'CAL_V1',
		threshold: 0.61,
		ecg_quality: 'VALID',
		monitoring_state: 'NORMAL_MONITORED_PATTERN',
		context: null,
		latency_ms: 3.1,
		preprocess_version: 'PREPROC_V1',
		alert_policy_id: 'ALERT_POLICY_V1',
		...overrides
	};
}

const error422: ErrorResponse = {
	contract_version: 'API_SCHEMA_V1',
	status_code: 422,
	error_type: 'UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW',
	message: 'INCOMPLETE_SIGNAL_WINDOW'
};

const error500: ErrorResponse = {
	contract_version: 'API_SCHEMA_V1',
	status_code: 500,
	error_type: 'INTERNAL_SERVER_ERROR',
	message: 'boom'
};

const error400: ErrorResponse = {
	contract_version: 'API_SCHEMA_V1',
	status_code: 400,
	error_type: 'NON_MONOTONIC_TIMESTAMP',
	message: 'timestamp not increasing'
};

describe('dashboard session: authoritative-state tests (Section 46)', () => {
	it('a success response sets the ECG window and appends a history point', () => {
		const session = createDashboardSession('sess-1');
		session.applySuccessfulWindow(request(1_000_000), response());
		expect(session.latestEcgWindow).toEqual([0.1, 0.2, 0.3]);
		expect(session.history).toHaveLength(1);
		expect(session.history[0].kind).toBe('success');
		expect(session.history[0].monitoring_state).toBe('NORMAL_MONITORED_PATTERN');
	});

	it('high probability with monitoring_state NORMAL renders NORMAL -- state is authoritative, not recomputed from probability', () => {
		const session = createDashboardSession('sess-1');
		session.applySuccessfulWindow(
			request(1_000_000),
			response({ source_domain_calibrated_probability: 0.99, threshold: 0.2, monitoring_state: 'NORMAL_MONITORED_PATTERN' })
		);
		expect(session.latestOutcome?.kind === 'success' && session.latestOutcome.response.monitoring_state).toBe(
			'NORMAL_MONITORED_PATTERN'
		);
	});

	it('low probability with monitoring_state POTENTIAL renders POTENTIAL -- state is authoritative, not recomputed from probability', () => {
		const session = createDashboardSession('sess-1');
		session.applySuccessfulWindow(
			request(1_000_000),
			response({ source_domain_calibrated_probability: 0.01, threshold: 0.9, monitoring_state: 'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN' })
		);
		expect(session.latestOutcome?.kind === 'success' && session.latestOutcome.response.monitoring_state).toBe(
			'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN'
		);
	});
});

describe('dashboard session: Section 17/27/41 HTTP outcome handling', () => {
	it('422 does not append a probability point but does leave a gap marker, and does not replace the ECG window', () => {
		const session = createDashboardSession('sess-1');
		session.applySuccessfulWindow(request(1_000_000), response());
		session.applySignalWindowError(error422);
		expect(session.history).toHaveLength(2);
		expect(session.history[1].kind).toBe('gap');
		expect(session.history[1].raw_probability).toBeNull();
		expect(session.history[1].monitoring_state).toBe('RECHECK_SENSOR');
		expect(session.latestEcgWindow).toEqual([0.1, 0.2, 0.3]); // unchanged from the prior success
	});

	it('500 does not append a probability point but does leave a gap marker, and does not retain a stale probability as current', () => {
		const session = createDashboardSession('sess-1');
		session.applySuccessfulWindow(request(1_000_000), response());
		session.applyServerError(error500);
		expect(session.history).toHaveLength(2);
		expect(session.history[1].kind).toBe('gap');
		expect(session.history[1].monitoring_state).toBe('SYSTEM_ERROR');
		expect(session.latestOutcome?.kind).toBe('server_error');
	});

	it('400 never appends any history entry at all', () => {
		const session = createDashboardSession('sess-1');
		session.applySuccessfulWindow(request(1_000_000), response());
		session.applyRequestError(error400);
		expect(session.history).toHaveLength(1); // only the earlier success
		expect(session.latestOutcome?.kind).toBe('request_error');
	});

	it('a transport error never fabricates a monitoring state', () => {
		const session = createDashboardSession('sess-1');
		session.applyTransportError('network down');
		expect(session.latestOutcome).toEqual({ kind: 'transport_error', message: 'network down' });
		expect(session.history).toHaveLength(0);
	});
});

describe('dashboard session: session isolation (Section 46/independent instances)', () => {
	it('two independently created sessions never share state', () => {
		const sessionA = createDashboardSession('A');
		const sessionB = createDashboardSession('B');
		sessionA.applySuccessfulWindow(request(1_000_000), response({ monitoring_state: 'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN' }));
		expect(sessionB.history).toHaveLength(0);
		expect(sessionB.latestOutcome).toBeNull();
		expect(sessionA.sessionId).toBe('A');
		expect(sessionB.sessionId).toBe('B');
	});
});
