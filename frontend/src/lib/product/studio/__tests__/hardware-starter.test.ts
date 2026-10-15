// @vitest-environment jsdom
// Recorded hardware lives INSIDE the single "Start a federation run" card and offers an honest starting-model choice.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import StudioRunStarter from '$lib/components/product/studio/StudioRunStarter.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FakeSocket, fakeBackend } from '../../__tests__/support';
import type { HardwareDemoRun, StudioCapabilities } from '../types';

const immediate = (cb: () => void) => { cb(); return 0; };
const HW = { available: true, source_mode: 'RECORDED_HARDWARE_DEMO' as const, model: 'HARDWARE_DEMO_MODEL_V1' as const, run_lengths: [3, 10], algorithms: ['FEDAVG', 'FEDPROX'],
	aggregation_modes: ['PLAIN', 'SECAGG_SHADOW'], secagg_scope: 'ROUND-1', fedprox_mu: 0.1, label_assignment: 'L', initialisations: ['HARDWARE_DEMO_MODEL_V1'], v2_initialisation: 'NOT_APPLICABLE',
	starting_models: [
		{ id: 'FRESH_SEEDED' as const, label: 'Fresh initialisation (seeded, untrained)', available: true, reason: null },
		{ id: 'WARM_START' as const, label: 'Pretrained: warm start from an earlier recorded-hardware run', available: true, reason: null },
		{ id: 'MODEL_V2_FINAL' as const, label: 'Pretrained V2 (MODEL_V2_FINAL)', available: false, reason: 'V2 is a 250 Hz ECG-window network; this model is tabular.' }] };
const caps = (hardware: typeof HW | undefined): StudioCapabilities => ({ studio_id: 'S', run_lengths: [3, 10], default_run_length: 3,
	ten_round: { available: true, initialisations: [], rounds_by_initialisation: {}, default_initialisation: 'FL_INIT_V2', source_modes: ['CANONICAL_SYNTHETIC'], algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: {}, expected_updates: 80 },
	three_round: { available: true, expected_updates: 24 }, ...(hardware ? { hardware_demo: hardware } : {}),
	evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'x', cohort_use_detail: 'd', claim_boundary: 'c' } } as StudioCapabilities);

const prior = { run_id: 'HDFLRUN-AAA', algorithm: 'FEDAVG', rounds_planned: 3, completed_at: '2026-10-15T00:00:00Z', model: { id: 'HARDWARE_DEMO_MODEL_V1' } } as unknown as HardwareDemoRun;
let started: unknown;
beforeEach(() => {
	FakeSocket.reset(); started = null;
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = Object.assign(fakeBackend(), {
		hardwareDemoSessions: () => Promise.resolve([{ id: 'HW-OK', started_at: '2026-10-15T00:00:00Z', stopped_at: '2026-10-15T00:01:00Z', record_count: 1200, trace_count: 1200, eligible: true },
			{ id: 'HW-EMPTY', started_at: '2026-10-15T00:00:00Z', stopped_at: '2026-10-15T00:00:05Z', record_count: 0, trace_count: 0, eligible: false }]),
		hardwareDemoRuns: () => Promise.resolve([prior]),
		hardwareDemoStart: (choice: unknown) => { started = choice; return Promise.reject(new Error('stop here')); }
	});
	setProductStore(new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u)));
});
afterEach(() => { cleanup(); setProductStore(null); });
const mount = (c: StudioCapabilities) => render(StudioRunStarter, { props: { capabilities: c, onStartThree: vi.fn(), onStartTen: vi.fn() } });

describe('recorded hardware inside the run starter', () => {
	it('offers the data-source switch only when the backend advertises hardware', () => {
		mount(caps(undefined));
		expect(screen.queryByTestId('data-source-hardware')).toBeNull();
	});
	it('selecting Recorded hardware swaps in the hardware form; V2 is shown as not applicable with the reason', async () => {
		mount(caps(HW));
		expect(screen.getByTestId('data-source-synthetic').getAttribute('aria-checked')).toBe('true');
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		expect(await screen.findByTestId('hardware-demo-starter')).toBeTruthy();
		expect(screen.getByTestId('hardware-demo-boundary').textContent).toContain('SYNTHETIC labels');
		const init = screen.getByTestId('hardware-demo-init') as HTMLSelectElement;
		expect([...init.options].map((o) => [o.value, o.disabled])).toEqual([['FRESH_SEEDED', false], ['WARM_START', false], ['MODEL_V2_FINAL', true]]);
		expect(screen.getByTestId('hardware-demo-v2-note').textContent).toContain('tabular');
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		expect((screen.getByTestId('hardware-demo-session-HW-EMPTY') as HTMLInputElement).disabled).toBe(true);
		expect(screen.queryByTestId('cfg-run-type')).toBeNull();     // the frozen synthetic 3-round form is not shown
	});
	it('warm start sends the chosen earlier run and the rounds come from the shared radio', async () => {
		mount(caps(HW));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await fireEvent.click(screen.getByTestId('rounds-10'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await fireEvent.change(screen.getByTestId('hardware-demo-init'), { target: { value: 'WARM_START' } });
		await fireEvent.change(screen.getByTestId('hardware-demo-algorithm'), { target: { value: 'FEDPROX' } });
		await fireEvent.click(screen.getByTestId('hardware-demo-start'));
		await waitFor(() => expect(started).toMatchObject({ session_ids: ['HW-OK'], run_length: 10, algorithm: 'FEDPROX', initialisation: 'WARM_START', warm_start_run_id: 'HDFLRUN-AAA' }));
	});
});
