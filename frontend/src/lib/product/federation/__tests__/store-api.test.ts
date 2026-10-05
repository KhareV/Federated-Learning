// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProductApiError, createProductClient, federationRunBody, federationSocketUrl } from '../../api';
import { FederationStore, REPLAY_NO_SOURCE } from '../state.svelte';
import { FakeSocket, fakeBackend, resetSeq } from '../../__tests__/support';
import { RUN_ID, eventStream } from './fixtures';

const immediate = (cb: () => void) => { cb(); return 0; };

describe('federation product client', () => {
	it('sends exactly the five frozen request fields with the frozen scenario and rounds', async () => {
		const sent: { url: string; body: Record<string, unknown> }[] = [];
		const client = createProductClient({ fetchImpl: (async (url: string, init: RequestInit) => { sent.push({ url, body: JSON.parse(String(init.body)) }); return new Response('{}', { status: 200 }); }) as unknown as typeof fetch });
		await client.createFederationRun({ run_type: 'LIVE_RUN', algorithm: 'FEDPROX', secagg_mode: 'SECAGG_SHADOW' });
		expect(sent[0].url).toBe('/product/v1/federation/runs');
		expect(Object.keys(sent[0].body).sort()).toEqual(['algorithm', 'planned_rounds', 'run_type', 'scenario_id', 'secagg_mode']);
		expect(sent[0].body).toMatchObject({ scenario_id: 'FL_SINGLE_RUN', planned_rounds: 3 });
		for (const forbidden of ['mu', 'learning_rate', 'optimizer', 'batch_size', 'model_id', 'base_model_id', 'checkpoint', 'candidate_id', 'calibration', 'threshold']) expect(sent[0].body).not.toHaveProperty(forbidden);
		expect(Object.keys(federationRunBody({ run_type: 'REPLAY', algorithm: 'FEDAVG', secagg_mode: 'PLAIN' }))).toHaveLength(5);
	});
	it('uses exactly the CAP-007 routes and the token-free same-origin WebSocket URL', async () => {
		const urls: string[] = [];
		const client = createProductClient({ getToken: async () => 'SECRET-TOKEN', fetchImpl: (async (url: string, init: RequestInit) => { urls.push(`${init.method} ${url}`); return new Response('{}', { status: 200 }); }) as unknown as typeof fetch });
		await client.federationOverview(); await client.federationClients(); await client.federationRuns(); await client.federationRun('R1'); await client.startFederationRun('R1'); await client.federationRounds('R1'); await client.models(); await client.model('MODEL_V2_FINAL');
		expect(urls).toEqual(['GET /product/v1/federation', 'GET /product/v1/federation/clients', 'GET /product/v1/federation/runs', 'GET /product/v1/federation/runs/R1', 'POST /product/v1/federation/runs/R1/start', 'GET /product/v1/federation/runs/R1/rounds', 'GET /product/v1/models', 'GET /product/v1/models/MODEL_V2_FINAL']);
		const url = federationSocketUrl('R1', { protocol: 'http:', host: 'localhost:5173' });
		expect(url).toBe('ws://localhost:5173/product/v1/federation/runs/R1/live');
		expect(url).not.toMatch(/token|secret|user|bearer|cookie/i);
	});
});

describe('federation store', () => {
	let backend: ReturnType<typeof fakeBackend>;
	let store: FederationStore;
	beforeEach(() => {
		FakeSocket.reset(); resetSeq();
		vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });
		backend = fakeBackend();
		store = new FederationStore(() => backend, immediate, (u) => new FakeSocket(u));
	});
	afterEach(() => store.closeLive());

	it('create -> open WebSocket -> start, in that order', async () => {
		const order: string[] = [];
		const create = backend.createFederationRun;
		backend.createFederationRun = async (c) => { order.push('create'); return create(c); };
		const start = backend.startFederationRun;
		backend.startFederationRun = async (id) => { order.push(`start(sockets=${FakeSocket.instances.length})`); return start(id); };
		await store.createAndStart({ run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'SECAGG_SHADOW' });
		expect(order).toEqual(['create', 'start(sockets=1)']);
		expect(FakeSocket.last.url).toBe(`ws://localhost:5173/product/v1/federation/runs/${RUN_ID}/live`);
		expect(backend.federationBodies).toHaveLength(1);
	});
	it('consumes a stream, reconnect resets and rebuilds from sequence 0 without double counting', async () => {
		await store.createAndStart({ run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'PLAIN' });
		const evs = eventStream();
		FakeSocket.last.open();
		for (const e of evs.slice(0, 60)) FakeSocket.last.send(e);
		expect(store.view.eventCount).toBe(60);
		FakeSocket.last.drop(1006);
		await new Promise((r) => setTimeout(r, 700));
		expect(store.view.eventCount).toBe(0); // reset before the replay
		FakeSocket.last.open();
		for (const e of evs) FakeSocket.last.send(e);
		expect(store.view.updateReadyCount).toBe(24);
		expect(store.view.runStatus).toBe('COMPLETED');
	});
	it('a sequence gap shows a stream error and stops consuming', async () => {
		await store.createAndStart({ run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'PLAIN' });
		const evs = eventStream();
		FakeSocket.last.open();
		FakeSocket.last.send(evs[0]); FakeSocket.last.send(evs[2]);
		expect(store.view.streamError?.reason).toBe('SEQUENCE_GAP');
		expect(store.socketStatus).toBe('DISCONNECTED');
	});
	it('REPLAY without a source shows the exact message and never switches to LIVE_RUN', async () => {
		backend.fed.createError = new ProductApiError(409, 'INVALID_LIFECYCLE_STATE', 'INVALID_STATE', 'NO_COMPLETED_SOURCE_RUN_FOR_REPLAY');
		await store.createAndStart({ run_type: 'REPLAY', algorithm: 'FEDAVG', secagg_mode: 'PLAIN' });
		expect(store.replayNoSource).toBe(true);
		expect(REPLAY_NO_SOURCE).toBe('NO COMPATIBLE LIVE RUN EXISTS YET. COMPLETE A LIVE RUN WITH THIS CONFIGURATION FIRST.');
		expect(backend.federationBodies).toHaveLength(1);
		expect((backend.federationBodies[0] as { run_type: string }).run_type).toBe('REPLAY');
		expect(FakeSocket.instances).toHaveLength(0);
	});
	it('clients are requested once even when called repeatedly (cold start is slow, never retried)', async () => {
		backend.fed.clientsDelayMs = 30;
		const a = store.loadClients(); const b = store.loadClients();
		expect(store.clientsPhase).toBe('PREPARING');
		await Promise.all([a, b]);
		expect(store.clientsPhase).toBe('READY');
		expect(backend.calls.filter((c) => c === 'federationClients')).toHaveLength(1);
	});
	it('backend guard: only ENABLED_ENGINEERING enables federation', () => {
		expect(FederationStore.backendEnabled('ENABLED_ENGINEERING')).toBe(true);
		expect(FederationStore.backendEnabled('NOT_IMPLEMENTED')).toBe(false);
		expect(FederationStore.backendEnabled(undefined)).toBe(false);
	});
});
