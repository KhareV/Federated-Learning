// @vitest-environment jsdom
// Recorded hardware lives INSIDE the single "Start a federation run" card and offers an honest starting-model choice.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import StudioRunStarter from '$lib/components/product/studio/StudioRunStarter.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FakeSocket, fakeBackend } from '../../__tests__/support';
import { parseCandidates } from '../parse';
import type { HardwareDemoRun, StudioCapabilities } from '../types';

const immediate = (cb: () => void) => { cb(); return 0; };
const HW = { available: true, source_mode: 'RECORDED_HARDWARE_DEMO' as const, model: 'HARDWARE_DEMO_MODEL_V1' as const, run_lengths: [3, 10], algorithms: ['FEDAVG', 'FEDPROX'],
	aggregation_modes: ['PLAIN', 'SECAGG_SHADOW'], secagg_scope: 'ROUND-1', fedprox_mu: 0.1, label_assignment: 'L', initialisations: ['HARDWARE_DEMO_MODEL_V1'], v2_initialisation: 'PRETRAINED_V2_FINE_TUNING',
	starting_models: [
		{ id: 'FRESH_SEEDED' as const, label: 'Fresh initialisation (seeded, untrained)', available: true, reason: null },
		{ id: 'WARM_START' as const, label: 'Pretrained: warm start from an earlier recorded-hardware run', available: true, reason: null },
		{ id: 'MODEL_V2_FINAL' as const, label: 'Pretrained V2 (MODEL_V2_FINAL)', available: true, reason: null, note: 'Federated fine-tuning of the verified pretrained V2 checkpoint on your recorded windows.' }] };
const caps = (hardware: typeof HW | undefined): StudioCapabilities => ({ studio_id: 'S', run_lengths: [3, 10], default_run_length: 3,
	ten_round: { available: true, initialisations: [], rounds_by_initialisation: {}, default_initialisation: 'FL_INIT_V2', source_modes: ['CANONICAL_SYNTHETIC'], algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: {}, expected_updates: 80 },
	three_round: { available: true, expected_updates: 24 }, ...(hardware ? { hardware_demo: hardware } : {}),
	evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'x', cohort_use_detail: 'd', claim_boundary: 'c' } } as StudioCapabilities);

const prior = { run_id: 'HDFLRUN-AAA', status: 'COMPLETED', algorithm: 'FEDAVG', rounds_planned: 3, completed_at: '2026-10-15T00:00:00Z', model: { id: 'HARDWARE_DEMO_MODEL_V1' } } as unknown as HardwareDemoRun;
let started: unknown;
let previewResult: unknown;
let candidatesResult: unknown[] = [];
const PREVIEW_OK = { sessions: [{ session_id: 'HW-OK', readings: 4800, windows: 57, usable: 40, train: 28, holdout: 8, by_quality: { VALID: 40, UNUSABLE: 17 }, excluded_reasons: { CLIPPING: 17 } }], train_windows: 28, holdout_windows: 8, min_train_windows: 16, min_holdout_windows: 4, eligible: true, reason: null, assumptions: {} };
const PREVIEW_BAD = { ...PREVIEW_OK, sessions: [{ ...PREVIEW_OK.sessions[0], usable: 0, train: 0, holdout: 0 }], train_windows: 0, holdout_windows: 0, eligible: false, reason: 'INSUFFICIENT_V2_WINDOWS: 0 training and 0 holdout windows usable; the unchanged PREPROC_V1 quality gate excluded: CLIPPING ×57.' };
beforeEach(() => {
	FakeSocket.reset(); started = null; previewResult = PREVIEW_OK; candidatesResult = [];
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = Object.assign(fakeBackend(), {
		hardwareDemoSessions: () => Promise.resolve([{ id: 'HW-OK', started_at: '2026-10-15T00:00:00Z', stopped_at: '2026-10-15T00:01:00Z', record_count: 1200, trace_count: 1200, eligible: true },
			{ id: 'HW-EMPTY', started_at: '2026-10-15T00:00:00Z', stopped_at: '2026-10-15T00:00:05Z', record_count: 0, trace_count: 0, eligible: false }]),
		hardwareDemoRuns: () => Promise.resolve([prior]),
		studioCandidates: () => Promise.resolve(parseCandidates(candidatesResult)),
		hardwareV2Preview: () => Promise.resolve(previewResult),
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
	it('selecting Recorded hardware swaps in the hardware form; pretrained V2 is a selectable starting model', async () => {
		mount(caps(HW));
		expect(screen.getByTestId('data-source-synthetic').getAttribute('aria-checked')).toBe('true');
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		expect(await screen.findByTestId('hardware-demo-starter')).toBeTruthy();
		expect(screen.getByTestId('hardware-demo-boundary').textContent).toContain('SYNTHETIC labels');
		const init = screen.getByTestId('hardware-demo-init') as HTMLSelectElement;
		expect([...init.options].map((o) => [o.value, o.disabled])).toEqual([['FRESH_SEEDED', false], ['WARM_START', false], ['MODEL_V2_FINAL', false]]);
		await waitFor(() => expect(init.value).toBe('MODEL_V2_FINAL'));      // pretrained V2 is the default, as for the synthetic cohort
		expect(screen.getByTestId('hardware-demo-v2-note')).toBeTruthy();
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
	it('an explicit choice of Fresh initialisation is kept (the pretrained-V2 default never overrides it) and is what is sent', async () => {
		mount(caps(HW));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		const init = screen.getByTestId('hardware-demo-init') as HTMLSelectElement;
		await waitFor(() => expect(init.value).toBe('MODEL_V2_FINAL'));          // untouched: the default
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await fireEvent.change(init, { target: { value: 'FRESH_SEEDED' } });
		await fireEvent.click(screen.getByTestId('rounds-10'));                    // other changes afterwards must not flip it back
		await fireEvent.change(screen.getByTestId('hardware-demo-algorithm'), { target: { value: 'FEDPROX' } });
		await new Promise((r) => setTimeout(r, 50));
		expect(init.value).toBe('FRESH_SEEDED');
		expect(screen.queryByTestId('hardware-demo-v2-note')).toBeNull();
		expect((screen.getByTestId('hardware-demo-start').textContent ?? '')).toContain('fresh initialisation');
		await fireEvent.click(screen.getByTestId('hardware-demo-start'));
		await waitFor(() => expect(started).toMatchObject({ session_ids: ['HW-OK'], initialisation: 'FRESH_SEEDED' }));
	});
	it('a History deep link opens Recorded hardware with that eligible session already chosen (and never an ineligible one)', async () => {
		render(StudioRunStarter, { props: { capabilities: caps(HW), onStartThree: vi.fn(), onStartTen: vi.fn(), dataSource: 'HARDWARE', preselectSession: 'HW-OK' } });
		await waitFor(() => expect((screen.getByTestId('hardware-demo-session-HW-OK') as HTMLInputElement).checked).toBe(true));
		cleanup();
		render(StudioRunStarter, { props: { capabilities: caps(HW), onStartThree: vi.fn(), onStartTen: vi.fn(), dataSource: 'HARDWARE', preselectSession: 'HW-EMPTY' } });
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-EMPTY')).toBeTruthy());
		expect((screen.getByTestId('hardware-demo-session-HW-EMPTY') as HTMLInputElement).checked).toBe(false);
	});
	it('pretrained V2 shows what the quality gate accepts and starts a MODEL_V2_FINAL run only when enough windows are usable', async () => {
		mount(caps(HW));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await fireEvent.change(screen.getByTestId('hardware-demo-init'), { target: { value: 'MODEL_V2_FINAL' } });
		expect(screen.getByTestId('hardware-demo-v2-note').textContent).toContain('verified pretrained MODEL_V2_FINAL');
		await waitFor(() => expect(screen.getByTestId('hardware-v2-preview').textContent).toContain('ENOUGH USABLE WINDOWS'));
		expect(screen.getByText('MODEL_V2_FINAL (fine-tuned)')).toBeTruthy();
		await fireEvent.click(screen.getByTestId('hardware-demo-start'));
		await waitFor(() => expect(started).toMatchObject({ session_ids: ['HW-OK'], run_length: 3, initialisation: 'MODEL_V2_FINAL' }));
		expect(started).not.toHaveProperty('warm_start_run_id');
	});
	it('pretrained V2 refuses to start (with the backend\'s reason) when the quality gate leaves too few windows', async () => {
		previewResult = PREVIEW_BAD;
		mount(caps(HW));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await fireEvent.change(screen.getByTestId('hardware-demo-init'), { target: { value: 'MODEL_V2_FINAL' } });
		await waitFor(() => expect(screen.getByTestId('hardware-v2-preview-reason').textContent).toContain('CLIPPING'));
		expect((screen.getByTestId('hardware-demo-start') as HTMLButtonElement).disabled).toBe(true);
	});
});

// The synthetic-cohort option for a recorded-hardware run: it supplies the seven synthetic peers (and the evaluation holdout) of a pretrained-V2 run only.
const withCohorts = (c: StudioCapabilities): StudioCapabilities => ({ ...c, ten_round: { ...c.ten_round, cohorts: [
	{ id: 'ORIGINAL', label: 'Original', description: 'The frozen cohort.', client_ids: ['SIM_FL_SITE_00'], evaluation_cohort_id: 'E1', cohort_use: 'u', claim_boundary: 'c', default: true },
	{ id: 'REALISTIC', label: 'Realistic', description: 'Premature ectopic beats with pauses.', client_ids: ['SIM_FL_SITE_00'], evaluation_cohort_id: 'E2', cohort_use: 'u', claim_boundary: 'c', default: false }] } });

describe('the cohort option on a recorded-hardware run', () => {
	it('the original cohort sends no cohort; the realistic cohort travels with a pretrained-V2 run', async () => {
		mount(withCohorts(caps(HW)));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await waitFor(() => expect(screen.getByTestId('hardware-v2-preview').textContent).toContain('ENOUGH USABLE WINDOWS'));
		await fireEvent.click(screen.getByTestId('hardware-demo-start'));
		await waitFor(() => expect(started).toMatchObject({ initialisation: 'MODEL_V2_FINAL' }));
		expect(started).not.toHaveProperty('cohort');
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		expect(screen.getByTestId('hardware-demo-v2-note').textContent).toContain('seven realistic synthetic peers');
		await fireEvent.click(screen.getByTestId('hardware-demo-start'));
		await waitFor(() => expect(started).toMatchObject({ session_ids: ['HW-OK'], initialisation: 'MODEL_V2_FINAL', cohort: 'REALISTIC' }));
	});
	it('the realistic cohort cannot be combined with a tabular starting model (no synthetic peers there)', async () => {
		mount(withCohorts(caps(HW)));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		await fireEvent.change(screen.getByTestId('hardware-demo-init'), { target: { value: 'FRESH_SEEDED' } });
		expect(screen.getByTestId('hardware-cohort-needs-v2').textContent).toContain('seven synthetic peers');
		expect((screen.getByTestId('hardware-demo-start') as HTMLButtonElement).disabled).toBe(true);
		await fireEvent.click(screen.getByTestId('cohort-original'));
		expect(screen.queryByTestId('hardware-cohort-needs-v2')).toBeNull();
		expect((screen.getByTestId('hardware-demo-start') as HTMLButtonElement).disabled).toBe(false);
	});
});


// A stored engineering candidate can be the starting model of a recorded-hardware run (the pretrained-V2 family): same topology, windows and quality gate, only R0 differs.
const CAND = (id: string, cohort: string) => ({ schema_version: 'STUDIO_ENGINEERING_CANDIDATE_V1', candidate_id: id, label: 'ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL', created_at: '2026-10-18T12:00:00+00:00', source_run_id: 'FL10RUN-AAA', source_kind: 'SYNTHETIC_COHORT',
	source_detail: {}, cohort, cohort_label: cohort, evaluation_cohort_id: 'E', run_length: 10, round_id: 10, algorithm: 'FEDAVG', secagg_mode: 'PLAIN', base_model: { model_id: 'MODEL_V2_FINAL' }, state_sha256: 'ab'.repeat(32), metrics: { AUPRC: 0.8 },
	promoted: false, deployed: false, registered_in_product_registry: false, used_for_monitoring: false });
const HW_WITH_CANDIDATES = { ...HW, starting_models: [...HW.starting_models, { id: 'CANDIDATE' as const, label: 'Stored engineering candidate (from your candidate library)', available: true, reason: null, note: 'starts the pretrained-V2 family from an earlier run' }] };

describe('a stored candidate as the starting model of a recorded-hardware run', () => {
	it('is offered, listed with its cohort, and sent with its id (the run is still the pretrained-V2 family)', async () => {
		candidatesResult = [CAND('FL10_CANDIDATE_FL10RUN-AAA', 'REALISTIC'), CAND('HDFL_CANDIDATE_B', 'ORIGINAL')];
		mount(caps(HW_WITH_CANDIDATES as unknown as typeof HW));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		await fireEvent.click(screen.getByTestId('hardware-demo-session-HW-OK'));
		await fireEvent.change(screen.getByTestId('hardware-demo-init'), { target: { value: 'CANDIDATE' } });
		const picker = (await screen.findByTestId('hardware-demo-candidate')) as HTMLSelectElement;
		await waitFor(() => expect(picker.options.length).toBe(2));
		expect(picker.options[0].textContent).toContain('realistic cohort');
		await waitFor(() => expect(screen.getByTestId('hardware-v2-preview').textContent).toContain('ENOUGH USABLE WINDOWS'));      // the quality-gate preview applies unchanged
		expect(screen.getByTestId('hardware-demo-v2-note').textContent).toContain('final state of the stored candidate');
		await fireEvent.change(picker, { target: { value: 'HDFL_CANDIDATE_B' } });
		expect(screen.getByTestId('hardware-demo-candidate-note').textContent).toContain('trained on the original cohort');
		await fireEvent.click(screen.getByTestId('hardware-demo-start'));
		await waitFor(() => expect(started).toMatchObject({ session_ids: ['HW-OK'], run_length: 3, initialisation: 'CANDIDATE', candidate_id: 'HDFL_CANDIDATE_B' }));
	});
	it('with no stored candidate the option is shown unavailable with its reason and cannot be started', async () => {
		const none = { ...HW, starting_models: [...HW.starting_models, { id: 'CANDIDATE' as const, label: 'Stored engineering candidate (from your candidate library)', available: false, reason: 'no completed run has produced an engineering candidate yet' }] };
		mount(caps(none as unknown as typeof HW));
		await fireEvent.click(screen.getByTestId('data-source-hardware'));
		await waitFor(() => expect(screen.getByTestId('hardware-demo-session-HW-OK')).toBeTruthy());
		const option = [...(screen.getByTestId('hardware-demo-init') as HTMLSelectElement).options].find((o) => o.value === 'CANDIDATE');
		expect(option?.disabled).toBe(true);
	});
});
