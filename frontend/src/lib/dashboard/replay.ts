// T034/C034 replay adapter: two clearly separated paths feeding the SAME dashboard session
// store created in T033 (session.svelte.ts). This module does no inference/calibration/
// threshold/episode computation of its own -- it only sequences outcomes through the existing
// apply* entry points, exactly like routes/monitoring/+page.svelte does for a live fetch. No
// second dashboard state engine is created.
//
// 1. applyRecordedResponseMetadata(): OFFLINE, METADATA-ONLY replay of an already-recorded
//    response log (reports/t034/*.jsonl). The log deliberately omits the 2500-sample ECG array
//    (Section 19: "do not duplicate all 2500 ECG values"), so this path CANNOT populate the
//    waveform panel -- state/history/metadata only. Used by offline semantic-analysis tests,
//    never by the canonical dashboard route.
// 2. runCanonicalRecordedReplay(): the CANONICAL path. Loads the full-fidelity frontend replay
//    bundle (frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json, built by
//    scripts/build_frontend_replay_bundle_c034.py from the frozen NPZ fixture), constructs a
//    real InferWindowRequest per event (full 2500-sample window), calls the real typed API
//    client, and feeds BOTH the real request and the real response/error into the session.
//    This is what the production /monitoring route uses -- the API response is always
//    authoritative; no prerecorded probability/state ever substitutes for it.

import type {
	ErrorResponse,
	InferWindowRequest,
	InferWindowResponse,
	MonitoringState
} from '$lib/api/nhm-v1';
import { nhmApi, type NhmApiClient } from '$lib/api/nhm-v1';
import type { DashboardSession } from './session.svelte';

// ---------------------------------------------------------------------------------------
// 1. Offline, metadata-only replay of an already-recorded response log (test/analysis-only)
// ---------------------------------------------------------------------------------------

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

/** Metadata-only request stub: an empty ECG array is explicit and intentional here -- this
 * path never claims to have received a real window. NEVER use this for canonical dashboard
 * replay (see runCanonicalRecordedReplay below, which always carries the full 2500 samples). */
function metadataOnlyRequestStub(sessionId: string, timestampUs: number): InferWindowRequest {
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

/** Feeds a parsed, already-recorded response log into an existing DashboardSession, in order.
 * OFFLINE / METADATA-ONLY -- never populates the waveform panel, never used by the canonical
 * dashboard route. */
export function applyRecordedResponseMetadata(
	session: DashboardSession,
	rows: ReplayResponseRow[]
): void {
	for (const row of rows) {
		if (row.http_status === 200) {
			const response = toInferWindowResponse(row);
			session.applySuccessfulWindow(
				metadataOnlyRequestStub(session.sessionId, row.timestamp_us),
				response
			);
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

// ---------------------------------------------------------------------------------------
// 2. Canonical recorded replay: full 2500-sample windows, real typed API calls, real
//    responses drive dashboard state. This is what the production /monitoring route uses.
// ---------------------------------------------------------------------------------------

/** One event in frontend/static/replay/<replay_id>.json (built by
 * scripts/build_frontend_replay_bundle_c034.py from the frozen NPZ fixture). Carries the full
 * recorded ECG window -- no label, prediction outcome, or SimulationTruth field. */
export interface ReplayBundleEvent {
	sequence_index: number;
	window_id: string;
	replay_id: string;
	timestamp_us: number;
	ecg: { samples: number[]; target_hz: 250; window_seconds: 10 };
	ecg_quality: 'VALID' | 'DEGRADED' | 'UNUSABLE';
	ppg_context: null;
	model_id: string;
	contract_version: 'API_SCHEMA_V1';
}

export interface ReplayBundle {
	replay_id: string;
	source_npz_sha256: string;
	source_manifest_participant_group_id: string;
	source_manifest_record_id: string;
	window_count: number;
	events: ReplayBundleEvent[];
	labels_included: false;
	prediction_outcome_included: false;
	simulation_truth_included: false;
}

/** Loads a browser-consumable replay bundle from /replay/<replayId>.json (served from
 * frontend/static/replay/ by SvelteKit's static asset handling). */
export async function loadReplayBundle(
	replayId: string,
	fetchImpl: typeof fetch = fetch
): Promise<ReplayBundle> {
	const response = await fetchImpl(`/replay/${replayId}.json`);
	if (!response.ok) {
		throw new Error(`Failed to load replay bundle ${replayId}: HTTP ${response.status}`);
	}
	return (await response.json()) as ReplayBundle;
}

export interface CanonicalReplayOptions {
	/** Presentation-only pacing between requests, in milliseconds. Never alters
	 * request.timestamp_us (which always comes from the recorded bundle). Defaults to 0
	 * (no delay) for fast/test mode. */
	stepDelayMs?: number;
	/** Called after each event is applied to the session, useful for progressive UI updates. */
	onEvent?: (event: ReplayBundleEvent, index: number) => void;
	/** Injectable typed API client -- defaults to the real singleton (nhmApi). Tests inject a
	 * client built with a mocked fetchImpl; production code never overrides this. */
	apiClient?: NhmApiClient;
}

function sleep(ms: number): Promise<void> {
	return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
}

/** Runs the canonical recorded replay: submits every bundle event, IN ORDER, through the real
 * typed nhmApi client against the real production API, and feeds both the real request and
 * the real response/error into the session. No prerecorded probability/state is ever used as
 * the authority -- the API response always is. Every successful event carries the full
 * 2500-sample recorded window into the session (never an empty stub). */
export async function runCanonicalRecordedReplay(
	session: DashboardSession,
	bundle: ReplayBundle,
	options: CanonicalReplayOptions = {}
): Promise<void> {
	const { stepDelayMs = 0, onEvent, apiClient = nhmApi } = options;
	const events = [...bundle.events].sort((a, b) => a.sequence_index - b.sequence_index);

	for (const event of events) {
		if (event.ecg.samples.length !== 2500) {
			throw new Error(
				`Canonical replay event ${event.sequence_index} does not carry 2500 samples (got ${event.ecg.samples.length}) -- refusing to send an incomplete/empty window.`
			);
		}

		const request: InferWindowRequest = {
			contract_version: event.contract_version,
			session_id: session.sessionId,
			timestamp_us: event.timestamp_us,
			ecg: event.ecg,
			ecg_quality: event.ecg_quality,
			ppg_context: event.ppg_context,
			model_id: event.model_id
		};

		const result = await apiClient.inferWindow(request);
		if (result.kind === 'success') {
			session.applySuccessfulWindow(request, result.data);
		} else if (result.kind === 'request_error') {
			session.applyRequestError(result.error);
		} else if (result.kind === 'signal_window_error') {
			session.applySignalWindowError(result.error);
		} else if (result.kind === 'server_error') {
			session.applyServerError(result.error);
		} else {
			session.applyTransportError(result.message);
		}

		onEvent?.(event, event.sequence_index);
		await sleep(stepDelayMs);
	}
}

export type { MonitoringState };
