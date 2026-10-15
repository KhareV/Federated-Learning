// @vitest-environment jsdom
// RUN-SWITCH TRANSACTION: selecting another run clears everything of the previous run at once, and a late response of the previous run is discarded.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FederationStore } from '../state.svelte';
import { FakeSocket, fakeBackend, resetSeq } from '../../__tests__/support';
import type { StudioRun } from '../../studio/types';

const immediate = (cb: () => void) => { cb(); return 0; };
const studioRun = (id: string, engine: StudioRun['engine'], source: StudioRun['source_mode']): StudioRun => ({
	run_id: id, run_length: 3, engine, origin: 'LIVE', run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'PLAIN', source_mode: source, status: 'COMPLETED', phase: 'DONE',
	current_round: 3, planned_rounds: 3, client_ids: [], candidate: null, failure: null, label: id, base_model: null, source_label: 'x', replay_of: null,
	evaluation: { available: true, source: 'LIVE', evaluation_run_id: id, reason: null, revision: 1 }, export_status: 'NOT_STARTED', created_at: null
});

describe('run switching', () => {
	let backend: ReturnType<typeof fakeBackend>;
	let store: FederationStore;
	beforeEach(() => {
		FakeSocket.reset(); resetSeq();
		vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });
		backend = fakeBackend();
		store = new FederationStore(() => backend, immediate, (u) => new FakeSocket(u));
	});
	afterEach(() => store.closeLive());

	it('a slow response for the previously selected run never replaces the current run', async () => {
		let releaseA: (r: StudioRun) => void = () => undefined;
		const slowA = new Promise<StudioRun>((resolve) => { releaseA = resolve; });
		(backend as unknown as { studioRun: (id: string) => Promise<StudioRun> }).studioRun = (id) => (id === 'FL10RUN-A' ? slowA : Promise.resolve(studioRun('HDFLRUN-B', 'HARDWARE_DEMO', 'RECORDED_HARDWARE')));
		const first = store.selectRun('FL10RUN-A');            // A is still loading ...
		await store.selectRun('HDFLRUN-B');                     // ... when the user switches to B
		expect(store.run?.run_id).toBe('HDFLRUN-B');
		releaseA(studioRun('FL10RUN-A', 'FL10_10R', 'CANONICAL_SYNTHETIC'));
		await first;
		expect(store.run?.run_id).toBe('HDFLRUN-B');            // A's late descriptor was discarded
		expect(store.view.runId).toBe('HDFLRUN-B');
	});
	it('clears the previous run immediately, before the next descriptor arrives', async () => {
		(backend as unknown as { studioRun: (id: string) => Promise<StudioRun> }).studioRun = (id) => Promise.resolve(studioRun(id, 'FL10_10R', 'CANONICAL_SYNTHETIC'));
		await store.selectRun('FL10RUN-A');
		expect(store.run?.run_id).toBe('FL10RUN-A');
		let release: (r: StudioRun) => void = () => undefined;
		(backend as unknown as { studioRun: (id: string) => Promise<StudioRun> }).studioRun = () => new Promise<StudioRun>((resolve) => { release = resolve; });
		const pending = store.selectRun('HDFLRUN-B');
		expect(store.run).toBeNull();                          // nothing of A is shown while B loads
		expect(store.view.runId).toBe('HDFLRUN-B');
		expect(store.view.eventCount).toBe(0);
		release(studioRun('HDFLRUN-B', 'HARDWARE_DEMO', 'RECORDED_HARDWARE'));
		await pending;
		expect(store.run?.run_id).toBe('HDFLRUN-B');
	});
});
