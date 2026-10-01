import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { createDashboardSession } from '../session.svelte';
import { applyReplayLog, parseReplayLog } from '../replay';
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

describe('replay adapter: public replay (real recorded production responses)', () => {
	const rows = readLog('reports/t034/public_replay_responses.jsonl');

	it('the saved replay log has 12 rows', () => {
		expect(rows).toHaveLength(12);
	});

	it('feeding the log through the existing session store reproduces the exact history', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST');
		applyReplayLog(session, rows);

		expect(session.history).toHaveLength(rows.length);
		expect(session.history.every((point) => point.kind === 'success')).toBe(true);

		const expectedStates = rows.map((row) => row.monitoring_state);
		expect(session.history.map((point) => point.monitoring_state)).toEqual(expectedStates);
	});

	it('the latest outcome matches the last row of the log', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-2');
		applyReplayLog(session, rows);
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
		applyReplayLog(session, rows);
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
		applyReplayLog(session, rows);
		expect(session.history.filter((point) => point.kind === 'gap')).toHaveLength(0);
	});

	it('does not reimplement monitoring-state computation: it is copied verbatim from the log', () => {
		const session = createDashboardSession('T034-FRONTEND-REPLAY-TEST-5');
		applyReplayLog(session, rows);
		for (const [index, row] of rows.entries()) {
			expect(session.history[index].monitoring_state).toBe(row.monitoring_state);
		}
	});
});

describe('replay adapter: simulation-engineering replay (context/error plumbing)', () => {
	const rows = readLog('reports/t034/sim_replay_responses.jsonl');

	it('has exactly 3 rows: 200, 200, 422', () => {
		expect(rows.map((row) => row.http_status)).toEqual([200, 200, 422]);
	});

	it('produces the correct gap count: zero gaps for the two 200s, one gap for the 422', () => {
		const session = createDashboardSession('T034-SIM-FRONTEND-REPLAY-TEST');
		applyReplayLog(session, rows);
		expect(session.history).toHaveLength(3);
		expect(session.history.filter((point) => point.kind === 'gap')).toHaveLength(1);
		expect(session.history[2].kind).toBe('gap');
		expect(session.history[2].monitoring_state).toBe('RECHECK_SENSOR');
	});

	it('no probability point is recorded for the 422 window', () => {
		const session = createDashboardSession('T034-SIM-FRONTEND-REPLAY-TEST-2');
		applyReplayLog(session, rows);
		expect(session.history[2].raw_probability).toBeNull();
		expect(session.history[2].source_domain_calibrated_probability).toBeNull();
	});
});

describe('replay adapter: no diagnosis wording leaks through replayed data', () => {
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

describe('replay adapter: separate controlled failure sequence', () => {
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
		applyReplayLog(session, rows);

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
