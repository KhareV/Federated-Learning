import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { createDashboardSession } from '../session.svelte';
import {
	applyRecordedResponseMetadata,
	loadReplayBundle,
	parseReplayLog,
	runCanonicalRecordedReplay,
	type ReplayBundle
} from '../replay';
import { createNhmApiClient } from '$lib/api/nhm-v1';
import { PROHIBITED_WORDING } from '../state-presentation';

// Walk up from this test file to find the repository root (reports/t034 lives outside
// /frontend) rather than hardcoding a directory depth.
function findRepoRoot(startDir: string): string {
	let dir = startDir;
	for (let i = 0; i < 10; i += 1) {
		try {
			readFileSync(path.join(dir, 'reports/t034/public_replay_responses.jsonl'));
			return dir;
		} catch {
			dir = path.dirname(dir);
		}
	}
	throw new Error('Could not locate reports/t034/public_replay_responses.jsonl');
}

const REPO_ROOT = findRepoRoot(__dirname);

function readLog(relativePath: string) {
	return parseReplayLog(readFileSync(path.join(REPO_ROOT, relativePath), 'utf-8'));
}

function readBundle(): ReplayBundle {
	return JSON.parse(
		readFileSync(path.join(REPO_ROOT, 'frontend/static/replay/PUBLIC_ECG_REPLAY_V1.json'), 'utf-8')
	) as ReplayBundle;
}

describe('offline metadata replay (applyRecordedResponseMetadata): public replay log', () => {
	const rows = readLog('reports/t034/public_replay_responses.jsonl');

	it('the saved replay log has 12 rows', () => {
		expect(rows).toHaveLength(12);
	});

	it('feeding the log through the existing session store reproduces the exact history', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST');
		applyRecordedResponseMetadata(session, rows);

		expect(session.history).toHaveLength(rows.length);
		expect(session.history.every((point) => point.kind === 'success')).toBe(true);

		const expectedStates = rows.map((row) => row.monitoring_state);
		expect(session.history.map((point) => point.monitoring_state)).toEqual(expectedStates);
	});

	it('the latest outcome matches the last row of the log', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-2');
		applyRecordedResponseMetadata(session, rows);
		const last = rows[rows.length - 1];
		expect(session.latestOutcome?.kind).toBe('success');
		if (session.latestOutcome?.kind === 'success') {
			expect(session.latestOutcome.response.monitoring_state).toBe(last.monitoring_state);
			expect(session.latestOutcome.response.model_id).toBe(last.model_id);
			expect(session.latestOutcome.response.calibration_domain).toBe(last.calibration_domain);
			expect(session.latestOutcome.response.alert_policy_id).toBe(last.alert_policy_id);
		}
	});

	it('technical metadata (model/calibration/policy IDs) is preserved exactly from the log', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-3');
		applyRecordedResponseMetadata(session, rows);
		for (const [index, row] of rows.entries()) {
			const point = session.history[index];
			expect(point.raw_probability).toBe(row.raw_probability);
			expect(point.source_domain_calibrated_probability).toBe(
				row.source_domain_calibrated_probability
			);
			expect(point.threshold).toBe(row.threshold);
		}
	});

	it('no gap markers appear for an all-200 replay', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-4');
		applyRecordedResponseMetadata(session, rows);
		expect(session.history.filter((point) => point.kind === 'gap')).toHaveLength(0);
	});

	it('does not reimplement monitoring-state computation: it is copied verbatim from the log', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-5');
		applyRecordedResponseMetadata(session, rows);
		for (const [index, row] of rows.entries()) {
			expect(session.history[index].monitoring_state).toBe(row.monitoring_state);
		}
	});

	it('this path never populates the waveform (empty samples stub, by design)', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-6');
		applyRecordedResponseMetadata(session, rows);
		expect(session.latestEcgWindow).toEqual([]);
	});
});

describe('offline metadata replay: simulation-engineering replay (context/error plumbing)', () => {
	const rows = readLog('reports/t034/sim_replay_responses.jsonl');

	it('has exactly 3 rows: 200, 200, 422', () => {
		expect(rows.map((row) => row.http_status)).toEqual([200, 200, 422]);
	});

	it('produces the correct gap count: zero gaps for the two 200s, one gap for the 422', () => {
		const session = createDashboardSession('T034-SIM-FRONTEND-REPLAY-TEST');
		applyRecordedResponseMetadata(session, rows);
		expect(session.history).toHaveLength(3);
		expect(session.history.filter((point) => point.kind === 'gap')).toHaveLength(1);
		expect(session.history[2].kind).toBe('gap');
		expect(session.history[2].monitoring_state).toBe('RECHECK_SENSOR');
	});

	it('no probability point is recorded for the 422 window', () => {
		const session = createDashboardSession('T034-SIM-FRONTEND-REPLAY-TEST-2');
		applyRecordedResponseMetadata(session, rows);
		expect(session.history[2].raw_probability).toBeNull();
		expect(session.history[2].source_domain_calibrated_probability).toBeNull();
	});
});

describe('offline metadata replay: no diagnosis wording leaks through replayed data', () => {
	it('no prohibited phrase appears in any replayed monitoring_state/calibration string field', () => {
		const rows = [
			...readLog('reports/t034/public_replay_responses.jsonl'),
			...readLog('reports/t034/sim_replay_responses.jsonl')
		];
		const text = JSON.stringify(rows).toLowerCase();
		for (const phrase of PROHIBITED_WORDING) {
			expect(text).not.toContain(phrase);
		}
	});
});

describe('offline metadata replay: separate controlled failure sequence', () => {
	const success = (sequence_index: number, timestamp_us: number) => ({
		sequence_index,
		timestamp_us,
		http_status: 200,
		model_id: 'MODEL_V1',
		preprocess_version: 'PREPROC_V1',
		alert_policy_id: 'ALERT_POLICY_V1',
		calibration_id: 'CAL_V1',
		calibration_domain: 'MIT-BIH-v1.0.0',
		calibration_patient_count: 3,
		raw_probability: 0.2,
		source_domain_calibrated_probability: 0.2,
		threshold: 0.6128035574269627,
		ecg_quality: 'VALID',
		monitoring_state: 'NO_ALERT',
		context_available: false
	});

	it('maps 200/422/200/500/200 without probability points for either error', () => {
		const rows = [
			success(0, 5_000_000),
			{
				sequence_index: 1,
				timestamp_us: 10_000_000,
				http_status: 422,
				error_type: 'UNUSABLE_SIGNAL',
				message: 'Signal window is unusable.'
			},
			success(2, 15_000_000),
			{
				sequence_index: 3,
				timestamp_us: 20_000_000,
				http_status: 500,
				error_type: 'INTERNAL_ERROR',
				message: 'Internal server error.'
			},
			success(4, 25_000_000)
		];
		const session = createDashboardSession('T034-CONTROLLED-FAILURE-FIXTURE');
		applyRecordedResponseMetadata(session, rows);

		expect(session.history).toHaveLength(5);
		expect(session.history.map((point) => point.kind)).toEqual([
			'success',
			'gap',
			'success',
			'gap',
			'success'
		]);
		expect(session.history[1].monitoring_state).toBe('RECHECK_SENSOR');
		expect(session.history[3].monitoring_state).toBe('SYSTEM_ERROR');
		expect(session.history[1].source_domain_calibrated_probability).toBeNull();
		expect(session.history[3].source_domain_calibrated_probability).toBeNull();
		expect(session.latestOutcome?.kind).toBe('success');
	});
});

// ---------------------------------------------------------------------------------------
// Canonical recorded replay (runCanonicalRecordedReplay): real request, real (mocked-fetch)
// API response drives state -- this is what the production /monitoring route uses.
// ---------------------------------------------------------------------------------------

describe('canonical recorded replay: frontend replay bundle identity', () => {
	const bundle = readBundle();

	it('has exactly 12 events, each with exactly 2500 samples, no labels/outcomes/truth', () => {
		expect(bundle.events).toHaveLength(12);
		expect(bundle.labels_included).toBe(false);
		expect(bundle.prediction_outcome_included).toBe(false);
		expect(bundle.simulation_truth_included).toBe(false);
		for (const event of bundle.events) {
			expect(event.ecg.samples).toHaveLength(2500);
			expect(event.ppg_context).toBeNull();
			expect(event.ecg.target_hz).toBe(250);
			expect(event.ecg.window_seconds).toBe(10);
		}
	});

	it('events are ordered and timestamps are exactly 5,000,000us apart', () => {
		const sequenceIndices = bundle.events.map((event) => event.sequence_index);
		expect(sequenceIndices).toEqual([...Array(12).keys()]);
		const timestamps = bundle.events.map((event) => event.timestamp_us);
		for (let i = 1; i < timestamps.length; i += 1) {
			expect(timestamps[i] - timestamps[i - 1]).toBe(5_000_000);
		}
		expect(timestamps[0]).toBe(10_000_000);
		expect(timestamps[timestamps.length - 1]).toBe(65_000_000);
	});
});

function mockFetchFor(bundle: ReplayBundle, responsesBySequence: Record<number, unknown>) {
	return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = typeof input === 'string' ? input : input.toString();
		if (url.endsWith('.json') && url.includes('/replay/')) {
			return new Response(JSON.stringify(bundle), { status: 200 });
		}
		if (url.endsWith('/v1/infer-window')) {
			const body = JSON.parse(init?.body as string);
			const sequence = bundle.events.find((event) => event.timestamp_us === body.timestamp_us)
				?.sequence_index;
			const response = responsesBySequence[sequence as number];
			return new Response(JSON.stringify(response), { status: 200 });
		}
		throw new Error(`Unexpected fetch: ${url}`);
	});
}

function realResponseFor(monitoringState: string, probability: number) {
	return {
		contract_version: 'API_SCHEMA_V1',
		timestamp_us: 0,
		model_id: 'MODEL_V1',
		target: 'AAMI_SVF_WINDOW_V1',
		raw_probability: probability,
		source_domain_calibrated_probability: probability,
		calibration_domain: 'MIT-BIH-v1.0.0',
		calibration_patient_count: 3,
		calibration_id: 'CAL_V1',
		threshold: 0.6128035574269627,
		ecg_quality: 'VALID',
		monitoring_state: monitoringState,
		context: null,
		latency_ms: 1.2,
		preprocess_version: 'PREPROC_V1',
		alert_policy_id: 'ALERT_POLICY_V1'
	};
}

describe('canonical recorded replay: real API responses drive dashboard state', () => {
	it('submits all 12 events in order, full samples, and the API response (not a prerecorded one) drives each history point', async () => {
		const bundle = readBundle();
		const responses: Record<number, unknown> = {};
		bundle.events.forEach((event, index) => {
			responses[index] = {
				...realResponseFor(
					index === 0 ? 'CONTEXT_UNAVAILABLE' : 'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN',
					index === 0 ? 0.1 : 0.9
				),
				timestamp_us: event.timestamp_us
			};
		});
		const fetchMock = mockFetchFor(bundle, responses);

		const session = createDashboardSession('T034-CANONICAL-REPLAY-TEST');
		const loaded = await loadReplayBundle('PUBLIC_ECG_REPLAY_V1', fetchMock as unknown as typeof fetch);
		const apiClient = createNhmApiClient({ fetchImpl: fetchMock as unknown as typeof fetch });
		await runCanonicalRecordedReplay(session, loaded, { stepDelayMs: 0, apiClient });

		expect(session.history).toHaveLength(12);
		expect(session.history.filter((p) => p.kind === 'gap')).toHaveLength(0);
		expect(session.history[0].monitoring_state).toBe('CONTEXT_UNAVAILABLE');
		expect(session.history[11].monitoring_state).toBe('POTENTIAL_ECTOPY_ASSOCIATED_PATTERN');
		// The API call count proves every event actually went through the real client, not a
		// prerecorded shortcut.
		const apiCalls = fetchMock.mock.calls.filter(([url]) =>
			(typeof url === 'string' ? url : url.toString()).endsWith('/v1/infer-window')
		);
		expect(apiCalls).toHaveLength(12);
	});

	it('the final ECG waveform carries exactly 2500 real recorded samples matching the sent window', async () => {
		const bundle = readBundle();
		const responses: Record<number, unknown> = {};
		bundle.events.forEach((event, index) => {
			responses[index] = { ...realResponseFor('NORMAL_MONITORED_PATTERN', 0.1), timestamp_us: event.timestamp_us };
		});
		const fetchMock = mockFetchFor(bundle, responses);

		const session = createDashboardSession('T034-WAVEFORM-TEST');
		const loaded = await loadReplayBundle('PUBLIC_ECG_REPLAY_V1', fetchMock as unknown as typeof fetch);
		const apiClient = createNhmApiClient({ fetchImpl: fetchMock as unknown as typeof fetch });
		await runCanonicalRecordedReplay(session, loaded, { stepDelayMs: 0, apiClient });

		expect(session.latestEcgWindow).toHaveLength(2500);
		expect(session.latestEcgWindow).toEqual(bundle.events[11].ecg.samples);
	});

	it('technical metadata (calibration/policy/model IDs) comes from the API response, not the bundle', async () => {
		const bundle = readBundle();
		const responses: Record<number, unknown> = {};
		bundle.events.forEach((event, index) => {
			responses[index] = { ...realResponseFor('NORMAL_MONITORED_PATTERN', 0.05), timestamp_us: event.timestamp_us };
		});
		const fetchMock = mockFetchFor(bundle, responses);
		const session = createDashboardSession('T034-METADATA-TEST');
		const loaded = await loadReplayBundle('PUBLIC_ECG_REPLAY_V1', fetchMock as unknown as typeof fetch);
		const apiClient = createNhmApiClient({ fetchImpl: fetchMock as unknown as typeof fetch });
		await runCanonicalRecordedReplay(session, loaded, { stepDelayMs: 0, apiClient });

		expect(session.latestOutcome?.kind).toBe('success');
		if (session.latestOutcome?.kind === 'success') {
			expect(session.latestOutcome.response.calibration_domain).toBe('MIT-BIH-v1.0.0');
			expect(session.latestOutcome.response.calibration_patient_count).toBe(3);
			expect(session.latestOutcome.response.alert_policy_id).toBe('ALERT_POLICY_V1');
			expect(session.latestOutcome.response.model_id).toBe('MODEL_V1');
		}
	});

	it('refuses to send a non-2500-sample event (canonical mode never supplies an empty/incomplete window)', async () => {
		const bundle = readBundle();
		const tampered: ReplayBundle = {
			...bundle,
			events: [{ ...bundle.events[0], ecg: { ...bundle.events[0].ecg, samples: [] } }]
		};
		const session = createDashboardSession('T034-EMPTY-WINDOW-GUARD');
		await expect(runCanonicalRecordedReplay(session, tampered, { stepDelayMs: 0 })).rejects.toThrow(
			/2500 samples/
		);
	});

	it('422/500 from the real API still map to RECHECK_SENSOR/SYSTEM_ERROR with no probability point', async () => {
		const bundle = readBundle();
		const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
			const url = typeof input === 'string' ? input : input.toString();
			if (url.includes('/replay/')) return new Response(JSON.stringify(bundle), { status: 200 });
			const body = JSON.parse(init?.body as string);
			if (body.timestamp_us === bundle.events[0].timestamp_us) {
				return new Response(
					JSON.stringify({
						contract_version: 'API_SCHEMA_V1',
						status_code: 422,
						error_type: 'UNUSABLE_OR_INCOMPLETE_SIGNAL_WINDOW',
						message: 'test'
					}),
					{ status: 422 }
				);
			}
			return new Response(
				JSON.stringify({
					contract_version: 'API_SCHEMA_V1',
					status_code: 500,
					error_type: 'INTERNAL_SERVER_ERROR',
					message: 'test'
				}),
				{ status: 500 }
			);
		});
		const session = createDashboardSession('T034-ERROR-MAPPING-TEST');
		const loaded = await loadReplayBundle('PUBLIC_ECG_REPLAY_V1', fetchMock as unknown as typeof fetch);
		const apiClient = createNhmApiClient({ fetchImpl: fetchMock as unknown as typeof fetch });
		await runCanonicalRecordedReplay(session, { ...loaded, events: loaded.events.slice(0, 2) }, {
			apiClient
		});

		expect(session.history[0].kind).toBe('gap');
		expect(session.history[0].monitoring_state).toBe('RECHECK_SENSOR');
		expect(session.history[0].raw_probability).toBeNull();
		expect(session.history[1].kind).toBe('gap');
		expect(session.history[1].monitoring_state).toBe('SYSTEM_ERROR');
		expect(session.history[1].raw_probability).toBeNull();
	});
});

describe('canonical recorded replay: production route wiring', () => {
	it('the canonical /monitoring route imports and uses the canonical replay controller', () => {
		const page = readFileSync(
			path.join(REPO_ROOT, 'frontend/src/routes/monitoring/+page.svelte'),
			'utf-8'
		);
		expect(page).toContain('runCanonicalRecordedReplay');
		expect(page).toContain('loadReplayBundle');
		expect(page).not.toContain('applyRecordedResponseMetadata');
	});

	it('does not reimplement monitoring-state computation inside the route', () => {
		const page = readFileSync(
			path.join(REPO_ROOT, 'frontend/src/routes/monitoring/+page.svelte'),
			'utf-8'
		);
		expect(page).not.toMatch(/probability\s*>=?\s*threshold/);
	});

	it('states PPG is unavailable and labels the mode as recorded replay, never live sensor', () => {
		const page = readFileSync(
			path.join(REPO_ROOT, 'frontend/src/routes/monitoring/+page.svelte'),
			'utf-8'
		);
		expect(page.toUpperCase()).toContain('RECORDED REPLAY');
		expect(page).not.toMatch(/live sensor/i);
	});
});
