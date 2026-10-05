// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FrontendAuth } from '../auth';
import { LiveSocket, MAX_RECONNECTS, type LiveSocketStatus } from '../socket';
import { ProductStore } from '../state.svelte';
import { FakeSocket, ev, fakeBackend, resetSeq, session as sess } from './support';

const immediate = (cb: () => void) => { cb(); return 0; };

describe('LiveSocket bounded reconnect policy', () => {
	beforeEach(() => FakeSocket.reset());
	it('retries at most MAX_RECONNECTS times, resetting derived state on every (re)connect, then reports DISCONNECTED', () => {
		const statuses: LiveSocketStatus[] = [];
		let resets = 0;
		const timers: (() => void)[] = [];
		const socket = new LiveSocket({
			url: 'ws://x/product/v1/sessions/S/live', factory: (u) => new FakeSocket(u),
			setTimer: (fn) => { timers.push(fn); return timers.length; }, clearTimer: () => {},
			handlers: { onReset: () => (resets += 1), onMessage: () => {}, onStatus: (s) => statuses.push(s) }
		});
		socket.connect();
		FakeSocket.last.open();
		for (let i = 0; i < MAX_RECONNECTS; i += 1) { FakeSocket.last.drop(1006); timers.shift()?.(); FakeSocket.last.open(); }
		FakeSocket.last.drop(1006);
		expect(statuses.at(-1)).toBe('DISCONNECTED');
		expect(timers).toHaveLength(0); // no infinite reconnect storm
		expect(FakeSocket.instances).toHaveLength(1 + MAX_RECONNECTS);
		expect(resets).toBe(1 + MAX_RECONNECTS); // a fresh deterministic rebuild each time
	});
	it('does not retry on a normal journal-complete close or on auth/ownership refusals; explicit reconnect works', () => {
		for (const code of [1000, 4401, 4403, 4404]) {
			FakeSocket.reset();
			const statuses: LiveSocketStatus[] = [];
			const s = new LiveSocket({ url: 'ws://x', factory: (u) => new FakeSocket(u), setTimer: () => 0, handlers: { onReset: () => {}, onMessage: () => {}, onStatus: (st) => statuses.push(st) } });
			s.connect(); FakeSocket.last.open(); FakeSocket.last.drop(code);
			expect(FakeSocket.instances).toHaveLength(1);
			expect(statuses.at(-1)).toBe(code === 1000 ? 'CLOSED_NORMAL' : 'DISCONNECTED');
		}
		const s = new LiveSocket({ url: 'ws://x', factory: (u) => new FakeSocket(u), setTimer: () => 0, handlers: { onReset: () => {}, onMessage: () => {}, onStatus: () => {} } });
		FakeSocket.reset(); s.connect(); FakeSocket.last.drop(4403); s.reconnect();
		expect(FakeSocket.instances).toHaveLength(2);
	});
});

function makeStore(backend = fakeBackend()) {
	FakeSocket.reset(); resetSeq();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });
	return { backend, store: new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u)) };
}
const live = (store: ProductStore) => store.live;

describe('ProductStore flows (fake backend: unit scope only)', () => {
	it('device flow: attach -> scan -> FOUND -> connect -> CONNECTED, state taken from the backend', async () => {
		const { store } = makeStore();
		await store.init();
		expect(store.authState.phase).toBe('AUTHENTICATED');
		await store.attachVirtualWearable('MIXED_MONITORING_SESSION');
		expect(store.selectedDevice?.connection_state).toBe('DETACHED');
		expect(store.scenarioFor(store.selectedDevice!.device_id)).toBe('MIXED_MONITORING_SESSION');
		await store.scan(store.selectedDevice!.device_id);
		expect(store.selectedDevice?.connection_state).toBe('FOUND');
		await store.connect(store.selectedDevice!.device_id);
		expect(store.selectedDevice?.connection_state).toBe('CONNECTED');
	});
	it('session flow: create opens the same-origin socket (no token in URL); start/stop go through the API', async () => {
		const { store, backend } = makeStore();
		await store.init();
		const created = await store.createSession('NHM_VIRTUAL_WEARABLE_01', 'MIXED_MONITORING_SESSION');
		expect(created?.state).toBe('DEVICE_READY');
		expect(FakeSocket.last.url).toBe('ws://localhost:5173/product/v1/sessions/SESS-1/live');
		expect(FakeSocket.last.url).not.toMatch(/token|\?/);
		await store.startSession();
		expect(store.activeSession?.state).toBe('MONITORING');
		await store.stopSession();
		expect(backend.calls).toEqual(['system', 'me', 'createSession', 'startSession', 'stopSession']);
		expect(backend.calls.some((c) => /infer/i.test(c))).toBe(false);
	});
	it('live events render into state; reconnect replays from 0 without double counting', async () => {
		const { store } = makeStore();
		await store.init();
		await store.createSession('NHM_VIRTUAL_WEARABLE_01', 'MIXED_MONITORING_SESSION');
		const first = FakeSocket.last;
		first.open();
		const script = () => {
			resetSeq();
			return [
				ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }),
				ev('device.status', { device_id: 'NHM_VIRTUAL_WEARABLE_01', device_state: 'STREAMING', adapter_type: 'SIMULATED', reason_code: null, recoverable: true }, { ts: 0 }),
				ev('waveform.chunk', { channel: 'ECG', unit: 'ADC_COUNTS', source_rate_hz: 360, first_sample_index: 0, first_sample_timestamp_us: 0, sample_count: 4, samples: [1, 2, null, 4] }),
				ev('quality.status', { ecg_quality: 'UNUSABLE', ppg_quality: null, ui_label: 'Recheck Sensor' }, { ts: 10 })
			];
		};
		for (const e of script()) first.send(e);
		expect(live(store).eventCount).toBe(4);
		expect(live(store).quality?.ui_label).toBe('Recheck Sensor');
		expect(live(store).monitoringState).toBeNull(); // 422/UNUSABLE-style window: no fabricated state
		expect(live(store).gaps).toEqual([{ start: 2, end: 2 }]);
		first.drop(1006); // transport drop: automatic reconnect, journal replays from 0
		await new Promise((r) => setTimeout(r, 700));
		const second = FakeSocket.last;
		expect(second).not.toBe(first);
		expect(live(store).eventCount).toBe(0); // derived state cleared before replay
		second.open();
		for (const e of script()) second.send(e);
		expect(live(store).eventCount).toBe(4); // exactly once, not 8
		expect(live(store).countsByType['waveform.chunk']).toBe(1);
	});
	it('a malformed event stops the stream visibly and never invents state', async () => {
		const { store } = makeStore();
		await store.init();
		await store.createSession('NHM_VIRTUAL_WEARABLE_01', 'MIXED_MONITORING_SESSION');
		FakeSocket.last.open();
		FakeSocket.last.send({ contract_version: 'PRODUCT_LIVE_EVENT_V1', event_type: 'federation.status', sequence_index: 0 });
		expect(live(store).streamError?.message).toContain('PRODUCT STREAM ERROR');
		expect(store.socketStatus).toBe('DISCONNECTED');
		expect(FakeSocket.last.closed).toBe(true);
	});
	it('a completed session close refreshes the persisted session from the API', async () => {
		const { store, backend } = makeStore();
		await store.init();
		await store.createSession('NHM_VIRTUAL_WEARABLE_01', 'MIXED_MONITORING_SESSION');
		backend.session = async () => sess('COMPLETED');
		FakeSocket.last.open();
		FakeSocket.last.send(ev('session.status', { session_state: 'COMPLETED', elapsed_ms: 5, reason_code: null }));
		await new Promise((r) => setTimeout(r, 10));
		expect(store.activeSession?.state).toBe('COMPLETED');
	});
});
