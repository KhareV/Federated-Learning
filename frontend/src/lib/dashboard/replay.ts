// T034 replay adapter: feeds a sequence of ALREADY-RECORDED real /v1/infer-window outcomes
// into the SAME dashboard session store created in T033 (session.svelte.ts). This module does
// no inference/calibration/threshold/episode computation of its own -- it only sequences
// pre-recorded outcomes through the existing apply* entry points, exactly like
// routes/monitoring/+page.svelte does for a live fetch. T034 does not create a second
// dashboard state engine.

import type { ErrorResponse, InferWindowRequest, InferWindowResponse } from '$lib/api/nhm-v1';
import type { DashboardSession } from './session.svelte';

/** One row as written by scripts/run_replay.py into reports/t034/public_replay_responses.jsonl
 * (or sim_replay_responses.jsonl). A 200 row carries the full response fields flattened; a
 * non-200 row carries http_status/error_type/message instead. */
export interface ReplayResponseRow {
	sequence_index: number;
	timestamp_us: number;
	http_status: number;
	// 200 fields
	model_id?: string;
	target?: string;
	preprocess_version?: string;
	contract_version?: string;
	alert_policy_id?: string;
	calibration_id?: string;
	calibration_domain?: string;
	calibration_patient_count?: number;
	raw_probability?: number | null;
	source_domain_calibrated_probability?: number | null;
	threshold?: number | null;
	ecg_quality?: string;
	monitoring_state?: string;
	context_available?: boolean | null;
	// error fields
	error_type?: string;
	message?: string;
}

function toInferWindowResponse(row: ReplayResponseRow): InferWindowResponse {
	return {
		contract_version: 'API_SCHEMA_V1',
		timestamp_us: row.timestamp_us,
		model_id: row.model_id ?? null,
		target: 'AAMI_SVF_WINDOW_V1',
		raw_probability: row.raw_probability ?? null,
		source_domain_calibrated_probability: row.source_domain_calibrated_probability ?? null,
		calibration_domain: row.calibration_domain ?? null,
		calibration_patient_count: row.calibration_patient_count ?? null,
		calibration_id: row.calibration_id ?? null,
		threshold: row.threshold ?? null,
		ecg_quality: (row.ecg_quality ?? 'VALID') as InferWindowResponse['ecg_quality'],
		monitoring_state: row.monitoring_state as InferWindowResponse['monitoring_state'],
		context:
			row.context_available == null
				? null
				: {
						ppg_quality: null,
						pr_ppg_bpm: null,
						spo2_pct: null,
						spo2_valid: false,
						hr_ecg_bpm: null,
						context_available: row.context_available,
						quality_warning: false,
						quality_warning_reasons: [],
						possible_pattern: false,
						ecg_hr_context_id: 'ECG_HR_CONTEXT_V2'
					},
		latency_ms: null,
		preprocess_version: row.preprocess_version ?? null,
		alert_policy_id: row.alert_policy_id ?? null
	};
}

function toErrorResponse(row: ReplayResponseRow): ErrorResponse {
	return {
		contract_version: 'API_SCHEMA_V1',
		status_code: row.http_status as 400 | 422 | 500,
		error_type: row.error_type ?? 'UNKNOWN',
		message: row.message ?? ''
	};
}

/** Parse one reports/t034/*.jsonl file's text content into rows. */
export function parseReplayLog(jsonlText: string): ReplayResponseRow[] {
	return jsonlText
		.split('\n')
		.map((line) => line.trim())
		.filter((line) => line.length > 0)
		.map((line) => JSON.parse(line) as ReplayResponseRow);
}

/** The replay log (reports/t034/public_replay_responses.jsonl) deliberately does not carry the
 * full 2500-sample ECG array (Section 19: "do not duplicate all 2500 ECG values"), so pure log
 * replay cannot populate the waveform panel -- only state/history/metadata. A request stub
 * with an empty samples array satisfies applySuccessfulWindow's signature without claiming a
 * real window was received. */
function emptyRequestStub(sessionId: string, timestampUs: number): InferWindowRequest {
	return {
		contract_version: 'API_SCHEMA_V1',
		session_id: sessionId,
		timestamp_us: timestampUs,
		ecg: { samples: [], target_hz: 250, window_seconds: 10 },
		ecg_quality: 'VALID',
		ppg_context: null,
		model_id: 'MODEL_V1'
	};
}

/** Feeds a parsed replay log into an existing DashboardSession, in order. */
export function applyReplayLog(session: DashboardSession, rows: ReplayResponseRow[]): void {
	for (const row of rows) {
		if (row.http_status === 200) {
			const response = toInferWindowResponse(row);
			session.applySuccessfulWindow(emptyRequestStub(session.sessionId, row.timestamp_us), response);
		} else if (row.http_status === 422) {
			session.applySignalWindowError(toErrorResponse(row));
		} else if (row.http_status === 400) {
			session.applyRequestError(toErrorResponse(row));
		} else if (row.http_status === 500) {
			session.applyServerError(toErrorResponse(row));
		} else {
			session.applyTransportError(`Unexpected HTTP status ${row.http_status}`);
		}
	}
}
