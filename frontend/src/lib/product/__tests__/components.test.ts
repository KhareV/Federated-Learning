// @vitest-environment jsdom
// Rendered-component tests: the ACTUAL route/shell components, fed by a store backed by the in-memory
// fake backend (unit scope). The canonical proof against the real backend is scripts/run_capstone_frontend_e2e.py.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { gotoMock } = vi.hoisted(() => ({ gotoMock: vi.fn(async () => {}) }));
vi.mock('$app/navigation', () => ({ goto: gotoMock, afterNavigate: () => {} }));
vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/app/device') } }));

import DemoBanner from '$lib/components/product/DemoBanner.svelte';
import WaveformPlot from '$lib/components/product/WaveformPlot.svelte';
import ProductShell from '$lib/components/product/ProductShell.svelte';
import SignIn from '../../../routes/sign-in/+page.svelte';
import DevicePage from '../../../routes/app/device/+page.svelte';
import MonitoringPage from '../../../routes/app/monitoring/+page.svelte';
import FederationPage from '../../../routes/app/federation/+page.svelte';
import OverviewPage from '../../../routes/app/+page.svelte';
import { FrontendAuth } from '../auth';
import { ProductStore, setProductStore } from '../state.svelte';
import { FakeSocket, ev, fakeBackend, resetSeq, systemInfo, type FakeBackend } from './support';

const immediate = (cb: () => void) => { cb(); return 0; };
let backend: FakeBackend;
let store: ProductStore;

function boot(system = systemInfo()) {
	FakeSocket.reset(); resetSeq();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	backend = fakeBackend(system);
	store = new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u));
	setProductStore(store);
}
beforeEach(() => { gotoMock.mockClear(); boot(); });
afterEach(() => { cleanup(); setProductStore(null); });

describe('sign-in', () => {
	it('DEMO backend: shows NHM OFFLINE FACULTY DEMO, discloses it is not Clerk, no password field, no Clerk init', async () => {
		render(SignIn);
		expect(await screen.findByText('NHM OFFLINE FACULTY DEMO')).toBeTruthy();
		expect(screen.getByText(/DEMO - NOT CLERK/)).toBeTruthy();
		expect(screen.getByText(/Not diagnostic/i)).toBeTruthy();
		expect(document.querySelector('input[type="password"]')).toBeNull();
		expect(store.auth.clerkWasInitialised).toBe(false);
		expect(backend.calls.slice(0, 1)).toEqual(['system']);
	});
	it('ENTER DEMO WORKSPACE verifies /me and then navigates to /app', async () => {
		render(SignIn);
		const button = await screen.findByRole('button', { name: 'ENTER DEMO WORKSPACE' });
		await fireEvent.click(button);
		await waitFor(() => expect(gotoMock).toHaveBeenCalledWith('/app'));
		expect(store.authState.identity?.user_id).toBe('demo:faculty');
		expect(backend.calls.filter((c) => c === 'me').length).toBeGreaterThanOrEqual(1);
	});
	it('CLERK backend without a publishable key: AUTHENTICATION UNAVAILABLE and no demo entry', async () => {
		boot(systemInfo({ auth_provider: 'CLERK', demo_mode: false }));
		render(SignIn);
		expect(await screen.findByText('AUTHENTICATION UNAVAILABLE')).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'ENTER DEMO WORKSPACE' })).toBeNull();
		expect(screen.queryByText('NHM OFFLINE FACULTY DEMO')).toBeNull();
	});
	it('unreachable backend: actionable local system error', async () => {
		FakeSocket.reset();
		const down = fakeBackend();
		down.system = async () => { throw new Error('connection refused'); };
		store = new ProductStore(new FrontendAuth({ createClient: () => down }), immediate);
		setProductStore(store);
		render(SignIn);
		expect(await screen.findByText('Product backend unavailable')).toBeTruthy();
		expect(screen.getByText(/run_capstone_product/)).toBeTruthy();
	});
});

describe('product shell + persistent Demo banner', () => {
	it('DEMO: the banner reads OFFLINE DEMO IDENTITY / NOT CLERK AUTHENTICATION and the shell shows first-class Federation navigation', async () => {
		await store.init();
		render(ProductShell);
		expect(screen.getByTestId('demo-banner').textContent).toContain('OFFLINE DEMO IDENTITY');
		expect(screen.getByTestId('demo-banner').textContent).toContain('NOT CLERK AUTHENTICATION');
		const nav = screen.getByRole('navigation', { name: 'Product sections' });
		for (const label of ['Overview', 'Device', 'Monitor', 'History', 'Federation', 'Models', 'Research', 'System']) {
			expect(nav.textContent).toContain(label);
		}
		expect(screen.getByTestId('identity-chip').textContent).toContain('demo:faculty');
	});
	it('CLERK mode: no demo banner', async () => {
		boot(systemInfo({ auth_provider: 'CLERK', demo_mode: false }));
		store.authState = { phase: 'AUTHENTICATED', mode: 'CLERK', system: systemInfo({ auth_provider: 'CLERK', demo_mode: false }), identity: null, error: null };
		render(ProductShell);
		expect(screen.queryByTestId('demo-banner')).toBeNull();
	});
	it('DemoBanner on its own is a persistent, visible note', () => {
		render(DemoBanner);
		expect(screen.getByRole('note').textContent).toMatch(/OFFLINE DEMO IDENTITY\s*NOT CLERK AUTHENTICATION/);
	});
});

describe('device page', () => {
	it('walks NO DEVICE -> attach -> scan -> FOUND -> connect -> CONNECTED with simulation labels and no hardware claim', async () => {
		await store.init();
		render(DevicePage);
		expect(screen.getByTestId('simulation-banner').textContent).toMatch(/SIMULATED WEARABLE.*NO PHYSICAL HARDWARE CONNECTED.*RESEARCH PROTOTYPE.*NOT DIAGNOSTIC/s);
		const select = screen.getByLabelText('Monitoring scenario') as HTMLSelectElement;
		expect([...select.options].map((o) => o.value)).toEqual(['NORMAL_MONITORING', 'CONTEXT_LOSS', 'POOR_SIGNAL', 'DISCONNECT_RECONNECT', 'MIXED_MONITORING_SESSION']);
		expect(select.value).toBe('MIXED_MONITORING_SESSION'); // recommended, not forced
		await fireEvent.click(screen.getByRole('button', { name: 'ATTACH NHM VIRTUAL WEARABLE' }));
		await screen.findByTestId('device-state');
		expect(screen.getByTestId('device-state').textContent).toBe('DETACHED');
		expect(screen.getByTestId('device-scenario').textContent).toBe('MIXED_MONITORING_SESSION');
		expect(document.body.textContent).toContain('NOT CONNECTED / NOT IMPLEMENTED');
		expect(document.body.textContent).toContain('SIMULATED');
		await fireEvent.click(screen.getByRole('button', { name: 'SCAN' }));
		await waitFor(() => expect(screen.getByTestId('device-state').textContent).toBe('FOUND'));
		await fireEvent.click(screen.getByRole('button', { name: 'PAIR / CONNECT' }));
		await waitFor(() => expect(screen.getByTestId('device-state').textContent).toBe('CONNECTED'));
		expect(backend.calls).toEqual(expect.arrayContaining(['createSimulatedDevice', 'scan', 'connect']));
	});
});

describe('monitoring page', () => {
	async function connectedMonitor() {
		await store.init();
		await store.attachVirtualWearable('MIXED_MONITORING_SESSION');
		await store.scan('NHM_VIRTUAL_WEARABLE_01');
		await store.connect('NHM_VIRTUAL_WEARABLE_01');
		render(MonitoringPage);
	}
	it('creates a session, opens the live socket, starts, and renders only backend events (quality != monitoring state)', async () => {
		await connectedMonitor();
		await fireEvent.click(screen.getByTestId('create-session'));
		await waitFor(() => expect(screen.getByTestId('session-id').textContent).toBe('SESS-1'));
		await fireEvent.click(screen.getByTestId('start-session'));
		const socket = FakeSocket.last; socket.open();
		socket.send(ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }));
		socket.send(ev('waveform.chunk', { channel: 'ECG', unit: 'ADC_COUNTS', source_rate_hz: 360, first_sample_index: 0, first_sample_timestamp_us: 0, sample_count: 6, samples: [1, 3, 2, null, null, 5] }));
		socket.send(ev('quality.status', { ecg_quality: 'UNUSABLE', ppg_quality: null, ui_label: 'Recheck Sensor' }, { ts: 100 }));
		await waitFor(() => expect(screen.getByTestId('quality-label').textContent).toBe('Recheck Sensor'));
		expect(screen.getByTestId('quality-state').textContent).toBe('UNUSABLE');
		expect(screen.getByTestId('monitoring-state-none')).toBeTruthy(); // UNUSABLE did NOT create a monitoring state
		expect(screen.getByTestId('context-unavailable')).toBeTruthy(); // UNUSABLE window: settled, no context
		expect(screen.getByTestId('waveform-plot').getAttribute('data-segments')).toBe('2');
		expect(screen.getByTestId('waveform-plot').getAttribute('data-visible-gaps')).toBe('1');
		expect(screen.getByTestId('gap-list').textContent).toContain('[3, 4]');
		expect(document.body.textContent).toContain('Simulated device-source ECG transport');
		expect(document.body.textContent).toContain('PPG waveform is unavailable');
	});
	it('shows the backend monitoring.state, the inference technical fields and a research-only probability section', async () => {
		await connectedMonitor();
		await fireEvent.click(screen.getByTestId('create-session'));
		await waitFor(() => screen.getByTestId('session-id'));
		const socket = FakeSocket.last; socket.open();
		socket.send(ev('quality.status', { ecg_quality: 'VALID', ppg_quality: 'VALID', ui_label: 'Signal Good' }, { ts: 50 }));
		socket.send(ev('context.snapshot', { hr_ecg_bpm: 72.5, pr_ppg_bpm: 71, spo2_pct: 97.5, spo2_valid: true, context_available: true, ppg_quality: 'VALID' }, { ts: 50 }));
		socket.send(ev('inference.result', { timestamp_us: 50, model_id: 'MODEL_V2_FINAL', calibration_id: 'CAL_V2', calibration_domain: 'SRC', preprocess_version: 'PREPROC_V1', alert_policy_id: 'ALERT_POLICY_V1', ecg_quality: 'VALID', monitoring_state: 'NORMAL_MONITORED_PATTERN', context: null, latency_ms: 12.5, raw_probability: 0.1, source_domain_calibrated_probability: 0.2, threshold: 0.6, probability_role: 'RESEARCH_TECHNICAL_METADATA' }, { ts: 50 }));
		socket.send(ev('monitoring.state', { monitoring_state: 'NORMAL_MONITORED_PATTERN', previous_state: null, reason_code: null }, { ts: 50 }));
		await waitFor(() => expect(screen.getByTestId('monitoring-state').textContent).toBe('NORMAL_MONITORED_PATTERN'));
		expect(screen.getByTestId('inf-model').textContent).toBe('MODEL_V2_FINAL');
		expect(screen.getByTestId('inf-cal').textContent).toContain('CAL_V2');
		expect(screen.getByText(/RESEARCH \/ TECHNICAL - not a risk score/)).toBeTruthy();
		expect(document.body.textContent).toContain('72.5');
		expect(document.body.textContent).toMatch(/Not a diagnosis, disease probability or clinical confidence/);
	});
	it('a device disconnect does not end the session; a system.error is a technical panel; a stream error is visible', async () => {
		await connectedMonitor();
		await fireEvent.click(screen.getByTestId('create-session'));
		await waitFor(() => screen.getByTestId('session-id'));
		const socket = FakeSocket.last; socket.open();
		socket.send(ev('session.status', { session_state: 'MONITORING', elapsed_ms: 0, reason_code: null }));
		socket.send(ev('device.status', { device_id: 'NHM_VIRTUAL_WEARABLE_01', device_state: 'DISCONNECTED', adapter_type: 'SIMULATED', reason_code: 'LINK_LOST', recoverable: true }));
		await waitFor(() => expect(screen.getByTestId('live-device-state').textContent).toBe('DISCONNECTED'));
		expect(screen.getByTestId('session-state').textContent).toBe('MONITORING');
		socket.send(ev('system.error', { error_code: 'INFERENCE_FAILED', message: 'x', recoverable: false, origin: 'INFERENCE' }));
		await waitFor(() => expect(screen.getByTestId('system-error').textContent).toContain('INFERENCE_FAILED'));
		expect(screen.getByText(/not a physiological state/i)).toBeTruthy();
		socket.send(ev('device.status', { device_id: 'NHM_VIRTUAL_WEARABLE_01', device_state: 'STREAMING', adapter_type: 'SIMULATED', reason_code: null, recoverable: true }, { seq: 99 }));
		await waitFor(() => expect(screen.getByTestId('stream-error').textContent).toContain('PRODUCT STREAM ERROR'));
	});
	it('completion shows the persistent session id and View Sessions', async () => {
		await connectedMonitor();
		await fireEvent.click(screen.getByTestId('create-session'));
		await waitFor(() => screen.getByTestId('session-id'));
		const socket = FakeSocket.last; socket.open();
		backend.stopSession = async () => (await import('./support')).session('COMPLETED');
		backend.session = async () => (await import('./support')).session('COMPLETED');
		socket.send(ev('session.status', { session_state: 'COMPLETED', elapsed_ms: 1000, reason_code: null }));
		const done = await screen.findByTestId('session-complete');
		expect(done.textContent).toContain('Session completed');
		expect(done.textContent).toContain('SESS-1');
		expect(done.textContent).toContain('View sessions');
	});
});

describe('overview + future-phase shells are honest', () => {
	it('overview shows real system identity, no fake metrics, and federation as not enabled', async () => {
		await store.init();
		render(OverviewPage);
		expect(document.body.textContent).toContain('MODEL_V2_FINAL');
		expect(document.body.textContent).toContain('SIMULATED_ONLY');
		expect(document.body.textContent).toContain('NOT YET ENABLED IN PRODUCT RUNTIME');
		expect(document.body.textContent).not.toMatch(/accuracy|F1|hospital|patients?\b/i);
	});
	it('federation page states the runtime is not enabled and shows no data', () => {
		render(FederationPage);
		const text = document.body.textContent ?? '';
		expect(text).toContain('FEDERATION PRODUCT RUNTIME NOT YET ENABLED IN THIS PHASE');
		expect(text).toContain('SIM_FL_SITE_00');
		expect(text).not.toMatch(/Delhi|Mumbai|Chennai|London|New York|Tokyo|Singapore/);
	});
});

describe('WaveformPlot gaps', () => {
	it('draws null runs as separate polylines with a visible gap marker (no zero fill)', () => {
		render(WaveformPlot, { segments: [{ start: 0, values: [1, 2, 3] }, { start: 6, values: [4, 5] }], start: 0, end: 8, capacity: 3600, gaps: [{ start: 3, end: 5 }] });
		const plot = screen.getByTestId('waveform-plot');
		expect(plot.querySelectorAll('polyline')).toHaveLength(2);
		expect(plot.querySelectorAll('[data-testid="waveform-gap"]')).toHaveLength(1);
		expect(plot.textContent).toContain('SOURCE GAP');
		for (const line of plot.querySelectorAll('polyline')) expect(line.getAttribute('points')).not.toMatch(/NaN/);
	});
});
