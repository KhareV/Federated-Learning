// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createProductClient, federationSocketUrl, type ProductClient } from '../../api';
import { display } from '../metrics';
import { parseEvalRecord, parseEvalRound, parseEvalSummary, parseExports, parseFigures, parseStudioRun, parseTables, StudioParseError } from '../parse';
import { StudioStore } from '../store.svelte';
import { digest, record, run, summary } from './fixtures';

const rawRecord = (r: ReturnType<typeof record>) => JSON.parse(JSON.stringify(r));

describe('strict parsers', () => {
	it('accepts a well-formed run and refuses a promoted or deployed candidate', () => {
		expect(parseStudioRun(run()).run_length).toBe(10);
		expect(() => parseStudioRun(run({ candidate: { candidate_id: 'C', promoted: true, deployed: false } as never }))).toThrow(StudioParseError);
		expect(() => parseStudioRun({ ...run(), run_length: 5 })).toThrow(/BAD_RUN_LENGTH/);
	});
	it('a queued, evaluating or failed round can never carry numbers; a completed round must', () => {
		expect(parseEvalRecord(rawRecord(record(1, 'QUEUED'))).metric_result).toBeNull();
		expect(() => parseEvalRecord({ ...rawRecord(record(1, 'QUEUED')), metric_result: { AUPRC: 0.9 } })).toThrow(/METRICS_REQUIRED_IFF_COMPLETED/);
		expect(() => parseEvalRecord({ ...rawRecord(record(1, 'COMPLETED')), metric_result: null })).toThrow(/METRICS_REQUIRED_IFF_COMPLETED/);
		expect(() => parseEvalRecord({ ...rawRecord(record(1, 'FAILED')), failure: null })).toThrow(/FAILURE_REQUIRED_IFF_FAILED/);
		expect(() => parseEvalRecord({ ...rawRecord(record(1, 'COMPLETED')), global_state_digest: 'zz' })).toThrow(/BAD_STATE_DIGEST/);
		expect(() => parseEvalRecord({ ...rawRecord(record(1, 'COMPLETED')), metric_result: { AUPRC: Number.POSITIVE_INFINITY } })).toThrow();
	});
	it('a summary containing another run\'s record is rejected (no bleed between runs)', () => {
		const ok = summary([record(0, 'COMPLETED')]);
		expect(parseEvalSummary(JSON.parse(JSON.stringify(ok))).records).toHaveLength(1);
		const mixed = JSON.parse(JSON.stringify({ ...ok, records: [record(0, 'COMPLETED'), record(1, 'COMPLETED', {}, 'FL10RUN-OTHER')] }));
		expect(() => parseEvalSummary(mixed)).toThrow(/FOREIGN_RECORD_RUN_ID/);
	});
	it('a not-yet-committed round parses as NOT_SUBMITTED with no data', () => {
		expect(parseEvalRound({ run_id: 'R', round_id: 7, evaluation_status: 'NOT_SUBMITTED', reason: 'not committed' })).toEqual({ run_id: 'R', round_id: 7, evaluation_status: 'NOT_SUBMITTED', reason: 'not committed' });
	});
	it('figure and table inventories must be complete and rectangular', () => {
		expect(() => parseFigures({ run_id: 'R', revision: 1, selected_round: null, source_label: 's', specs: {} })).toThrow(/FIGURE_INVENTORY_INCOMPLETE/);
		expect(() => parseTables({ run_id: 'R', revision: 1, source_label: 's', tables: {} })).toThrow(/TABLE_INVENTORY_INCOMPLETE/);
		const tables = Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`T${i}`, { title: 't', columns: ['a', 'b'], rows: [[1, 2]], caption: 'c', sources: [], synthetic_label: 's', availability: 'AVAILABLE' }]));
		expect(Object.keys(parseTables({ run_id: 'R', revision: 1, source_label: 's', tables }).tables)).toHaveLength(12);
		tables.T3.rows = [[1]] as never;
		expect(() => parseTables({ run_id: 'R', revision: 1, source_label: 's', tables })).toThrow(/ROW_WIDTH/);
		expect(parseExports({ status: 'PREPARING', run_id: 'R', message: 'EXPORT PREPARING' }).status).toBe('PREPARING');
	});
});

describe('honest metric display', () => {
	it('shows pending, failed and undefined states and never a zero for a missing value', () => {
		expect(display(undefined, 'AUPRC')).toMatchObject({ text: 'NOT YET AVAILABLE', tone: 'pending' });
		expect(display(record(1, 'QUEUED'), 'AUPRC')).toMatchObject({ text: 'QUEUED', tone: 'pending' });
		expect(display(record(1, 'EVALUATING'), 'F1')).toMatchObject({ text: 'EVALUATING', tone: 'pending' });
		expect(display(record(1, 'FAILED'), 'F1')).toMatchObject({ text: 'FAILED — X', tone: 'failed' });
		const d = display(record(1, 'COMPLETED'), 'negative_predictive_value');
		expect(d.tone).toBe('undefined');
		expect(d.text).toBe('UNDEFINED — no negative predictions (TN+FN = 0)');
	});
	it('prints source numbers at 6 decimals and keeps the exact value; a genuine zero stays a zero', () => {
		const r = record(1, 'COMPLETED');
		expect(display(r, 'AUPRC')).toMatchObject({ text: '0.911570', full: '0.911570123456789', tone: 'value' });
		expect(display(r, 'specificity').text).toBe('0');
		expect(display(r, 'TP', 'count').text).toBe('307');
	});
});

describe('round-scoped api client and sockets', () => {
	it('uses the studio routes and keeps 3-round sockets on the original product route', async () => {
		const urls: string[] = [];
		const client = createProductClient({ fetchImpl: (async (url: string, init: RequestInit) => { urls.push(`${init.method} ${url}`); return new Response('{}', { status: 200 }); }) as never });
		for (const call of [() => client.studioRun('FL10RUN-A'), () => client.studioEvaluation('R1'), () => client.studioEvaluationRound('R1', 4), () => client.studioRoundDetail('R1', 4), () => client.studioFigures('R1', 6), () => client.studioFigures('R1'), () => client.studioTables('R1'), () => client.studioExports('R1')]) {
			await call().catch(() => undefined);
		}
		expect(urls).toEqual(['GET /product/v1/studio/runs/FL10RUN-A', 'GET /product/v1/studio/runs/R1/evaluation', 'GET /product/v1/studio/runs/R1/evaluation/4', 'GET /product/v1/studio/runs/R1/rounds/4', 'GET /product/v1/studio/runs/R1/figures?round=6',
			'GET /product/v1/studio/runs/R1/figures', 'GET /product/v1/studio/runs/R1/tables', 'GET /product/v1/studio/runs/R1/exports']);
		const loc = { protocol: 'https:', host: 'h' };
		expect(federationSocketUrl('FEDRUN-X', loc)).toBe('wss://h/product/v1/federation/runs/FEDRUN-X/live');
		expect(federationSocketUrl('FL10RUN-X', loc)).toBe('wss://h/product/v1/studio/runs/FL10RUN-X/live');
		expect(federationSocketUrl('recorded-A', loc)).toBe('wss://h/product/v1/studio/runs/recorded-A/live');
		expect(federationSocketUrl('FL10RUN-X', loc)).not.toMatch(/token|secret|user|bearer|cookie/i);
	});
	it('a 10-round start sends exactly run_length and source_mode (no algorithm, threshold or calibration field)', async () => {
		const sent: unknown[] = [];
		const client = createProductClient({ fetchImpl: (async (_u: string, init: RequestInit) => { sent.push(JSON.parse(String(init.body))); return new Response('{}', { status: 200 }); }) as never });
		await client.studioStartTenRound({ run_length: 10, source_mode: 'LIVE_MONITORED_SITE_00' }).catch(() => undefined);
		expect(sent[0]).toEqual({ run_length: 10, source_mode: 'LIVE_MONITORED_SITE_00' });
	});
});

describe('Studio store: shared selected-round state, pending evaluation and run isolation', () => {
	let api: Record<string, ReturnType<typeof vi.fn>>;
	let store: StudioStore;
	const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
	const records = (n: number, pendingFrom: number) => Array.from({ length: n }, (_, i) => record(i, i < pendingFrom ? 'COMPLETED' : i === pendingFrom ? 'EVALUATING' : 'QUEUED'));
	beforeEach(() => {
		vi.useFakeTimers();
		api = {
			studioRun: vi.fn(async () => run()), studioEvaluation: vi.fn(async () => summary(records(4, 2))), studioExports: vi.fn(async () => ({ status: 'NOT_STARTED', run_id: 'FL10RUN-AAA' })),
			studioEvaluationRound: vi.fn(async (_id: string, r: number) => ({ ...record(r, 'COMPLETED'), participant_metrics: {}, curves: null })), studioRoundDetail: vi.fn(async (_id: string, r: number) => ({ run_id: 'FL10RUN-AAA', round_id: r, committed: true, round: null, client_rounds: [], batches: [], state: null })),
			studioFigures: vi.fn(), studioTables: vi.fn(), studioCapabilities: vi.fn(async () => null)
		};
		store = new StudioStore(() => api as unknown as ProductClient);
	});
	afterEach(() => { store.stopPolling(); vi.useRealTimers(); });

	it('follow-live tracks the actual round; a manual selection survives new events; RETURN TO LIVE restores following', async () => {
		store.track('FL10RUN-AAA'); await flush();
		store.setProgress(3, 2);
		expect(store.followLive).toBe(true);
		expect(store.selectedRound).toBe(3);
		store.selectRound(1);
		expect(store.followLive).toBe(false);
		store.setProgress(6, 5);                                   // training advances; the user's historical choice must not move
		expect(store.selectedRound).toBe(1);
		store.returnToLive();
		expect(store.selectedRound).toBe(6);
		store.selectRound(99);                                     // out of range is ignored
		expect(store.followLive).toBe(true);
	});
	it('only measured rounds have metrics: the latest evaluated round is shown (labelled) while the live round is still pending', async () => {
		store.track('FL10RUN-AAA'); await flush();
		store.setProgress(3, 3);
		expect(store.statusOf(0)).toBe('COMPLETED');
		expect(store.statusOf(2)).toBe('EVALUATING');
		expect(store.statusOf(3)).toBe('QUEUED');
		expect(store.statusOf(8)).toBe('NOT_SUBMITTED');
		expect(store.latestEvaluatedRound).toBe(1);
		expect(store.selectedRound).toBe(3);
		expect(store.metricRound).toBe(1);                         // substitution is explicit in the UI; the selected round itself stays R3
		store.selectRound(0);
		expect(store.metricRound).toBe(0);
	});
	it('polls only while something is pending and stops when the run and every evaluation are settled', async () => {
		store.track('FL10RUN-AAA'); await flush();
		const before = api.studioEvaluation.mock.calls.length;
		await vi.advanceTimersByTimeAsync(2100);
		expect(api.studioEvaluation.mock.calls.length).toBeGreaterThan(before);
		api.studioRun.mockResolvedValue(run({ status: 'COMPLETED', phase: 'DONE', export_status: 'READY' }));
		api.studioEvaluation.mockResolvedValue(summary(Array.from({ length: 11 }, (_, i) => record(i, 'COMPLETED'))));
		api.studioExports.mockResolvedValue({ status: 'READY', run_id: 'FL10RUN-AAA' });
		await vi.advanceTimersByTimeAsync(2100); await flush();
		const settled = api.studioEvaluation.mock.calls.length;
		await vi.advanceTimersByTimeAsync(10000);
		expect(api.studioEvaluation.mock.calls.length).toBe(settled);   // no further polling
	});
	it('a committed round triggers an immediate refresh instead of waiting for the next poll', async () => {
		store.track('FL10RUN-AAA'); await flush();
		store.setProgress(2, 1); await flush();
		const calls = api.studioEvaluation.mock.calls.length;
		store.setProgress(3, 2); await flush();
		expect(api.studioEvaluation.mock.calls.length).toBe(calls + 1);
		store.setProgress(3, 2); await flush();                       // no new commit: no extra request
		expect(api.studioEvaluation.mock.calls.length).toBe(calls + 1);
	});
	it('switching runs clears every run-scoped cache first and drops a late response of the previous run', async () => {
		let release: (value: unknown) => void = () => undefined;
		api.studioEvaluation.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
		store.track('FL10RUN-AAA'); await flush();                    // run A's evaluation request is in flight
		store.selectRound(2);
		api.studioRun.mockResolvedValue(run({ run_id: 'FL10RUN-BBB' }));
		api.studioEvaluation.mockResolvedValue(summary([record(0, 'COMPLETED', {}, 'FL10RUN-BBB')]));
		store.track('FL10RUN-BBB');                                    // user switches to run B
		expect(store.summary).toBeNull();
		expect(store.run).toBeNull();
		expect(store.followLive).toBe(true);
		expect(store.manualRound).toBeNull();
		expect(store.selectedClientId).toBeNull();
		await flush();
		release(summary(records(4, 3)));                               // run A's slow response finally arrives
		await flush();
		expect(store.run?.run_id).toBe('FL10RUN-BBB');
		expect(store.summary?.run_id).toBe('FL10RUN-BBB');
		expect(store.records.every((r) => r.run_id === 'FL10RUN-BBB')).toBe(true);
	});
	it('a run without captured evaluation requests no figures or evaluation and shows no data', async () => {
		api.studioRun.mockResolvedValue(run({ evaluation: { available: false, source: 'LIVE', evaluation_run_id: 'FL10RUN-AAA', reason: 'RUN_PREDATES_LIVE_EVALUATION', revision: 0 }, status: 'COMPLETED', phase: 'DONE' }));
		store.track('FL10RUN-AAA'); await flush();
		await store.ensureFigures(); await store.ensureTables(); await store.loadRound(2);
		expect(api.studioEvaluation).not.toHaveBeenCalled();
		expect(api.studioFigures).not.toHaveBeenCalled();
		expect(store.records).toEqual([]);
	});
});
