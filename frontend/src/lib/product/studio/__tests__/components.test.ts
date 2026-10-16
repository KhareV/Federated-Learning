// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AnalysisTabs from '$lib/components/product/studio/AnalysisTabs.svelte';
import ClientGrid from '$lib/components/product/federation/ClientGrid.svelte';
import MetricCards from '$lib/components/product/studio/MetricCards.svelte';
import RunStatusStrip from '$lib/components/product/studio/RunStatusStrip.svelte';
import StudioRunStarter from '$lib/components/product/studio/StudioRunStarter.svelte';
import { FederationLiveModel } from '../../federation/live-model';
import { ownerBoundClientId } from '../../federation/participation';
import { FederationStore, studioRunToFederationRun } from '../../federation/state.svelte';
import { RUN_ID, eventStream } from '../../federation/__tests__/fixtures';
import { FakeSocket, fakeBackend, resetSeq } from '../../__tests__/support';
import type { ProductClient } from '../../api';
import { StudioStore } from '../store.svelte';
import type { StudioCapabilities } from '../types';
import { getProductStore } from '../../state.svelte';
import { record, run, summary } from './fixtures';

const immediate = (cb: () => void) => { cb(); return 0; };
const text = () => document.body.textContent ?? '';
afterEach(() => cleanup());

const CAPS: StudioCapabilities = { studio_id: 'S', run_lengths: [3, 10], default_run_length: 3,
	ten_round: { available: true, source_modes: ['CANONICAL_SYNTHETIC', 'LIVE_MONITORED_SITE_00'], algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: { FEDPROX: 'not implemented or verified by the 10-round engine', SECAGG_SHADOW: 'not implemented or verified by the 10-round engine' }, expected_updates: 80 },
	three_round: { available: true, expected_updates: 24 }, evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST', cohort_use_detail: 'd', claim_boundary: 'c' } };

describe('FederationStore: 10-round start and per-round historical views', () => {
	let store: FederationStore;
	let backend: ReturnType<typeof fakeBackend>;
	beforeEach(() => {
		FakeSocket.reset(); resetSeq();
		vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });
		backend = fakeBackend();
		backend.studioStartTenRound = async () => run({ run_id: 'FL10RUN-AAA' });
		backend.studioRuns = async () => [run({ run_id: 'FL10RUN-AAA' }), run({ run_id: 'recorded-A', origin: 'RECORDED', run_type: 'REPLAY', status: 'COMPLETED' })];
		store = new FederationStore(() => backend, immediate, (u) => new FakeSocket(u));
	});
	afterEach(() => store.closeLive());

	it('starts a 10-round run through the studio route, opens the typed studio journal, and the 3-round route is not used', async () => {
		const started = await store.startTenRound({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC' });
		expect(started).toMatchObject({ run_id: 'FL10RUN-AAA', planned_rounds: 10, run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'PLAIN', engineering_only: true });
		expect(FakeSocket.last.url).toBe('ws://localhost:5173/product/v1/studio/runs/FL10RUN-AAA/live');
		expect(backend.calls).not.toContain('createFederationRun');
		await store.loadRuns();
		expect(store.runs.map((r) => r.run_id)).toContain('recorded-A');
	});
	it('rebuilds a round exactly as it was when it finished, only from this run\'s events, and never mutates the live view', async () => {
		store.openLive(RUN_ID);
		FakeSocket.last.open();
		const events = eventStream();
		for (const e of events.slice(0, 40)) FakeSocket.last.send(e);
		expect(store.viewAtRound(1)).toBeNull();                                    // round 1 has not finished: no fake history
		for (const e of events.slice(40)) FakeSocket.last.send(e);
		const live = JSON.parse(JSON.stringify(store.view));
		const r1 = store.viewAtRound(1)!, r2 = store.viewAtRound(2)!, r3 = store.viewAtRound(3)!, r0 = store.viewAtRound(0)!;
		expect(r0.updateReadyCount).toBe(0);
		expect([r1.updateReadyCount, r2.updateReadyCount, r3.updateReadyCount]).toEqual([8, 16, 24]);
		expect([r1.submittedCount, r2.submittedCount, r3.submittedCount]).toEqual([8, 16, 24]);
		expect(r1.currentRound).toBe(1);
		expect(r1.clients[0].milestones).toEqual({ 1: 1 });                          // round 1 evidence only
		expect(Object.keys(r2.clients[0].updateDigests)).toEqual(['1', '2']);
		expect(r1.rounds).toHaveLength(1);
		expect(r1.runStatus).toBe('RUNNING');                                         // the run was still running when round 1 finished
		expect(store.view.runStatus).toBe('COMPLETED');
		expect(JSON.parse(JSON.stringify(store.view))).toEqual(live);
		expect(store.viewAtRound(1)).toBe(r1);                                        // memoized
	});
	it('reconnecting resets the log: no event of the earlier connection survives', async () => {
		store.openLive(RUN_ID);
		FakeSocket.last.open();
		for (const e of eventStream().slice(0, 100)) FakeSocket.last.send(e);
		expect(store.eventLog.length).toBe(100);
		FakeSocket.last.drop(1006);
		await new Promise((r) => setTimeout(r, 700));
		expect(store.eventLog.length).toBe(0);
		expect(store.viewAtRound(1)).toBeNull();
	});
	it('adapts a studio descriptor without inventing fields', () => {
		const adapted = studioRunToFederationRun(run({ run_id: 'recorded-B', origin: 'RECORDED', run_type: 'REPLAY', status: 'COMPLETED', current_round: 10 }));
		expect(adapted).toMatchObject({ run_id: 'recorded-B', run_type: 'REPLAY', planned_rounds: 10, current_round: 10, status: 'COMPLETED', candidate_ids: [], started_at_us: null });
	});
});

describe('round-count selector and run starter', () => {
	it('defaults to 3 rounds, shows the expected (not completed) counts, and keeps the original form for 3 rounds', () => {
		render(StudioRunStarter, { props: { capabilities: CAPS, onStartThree: vi.fn(), onStartTen: vi.fn() } });
		expect(screen.getByTestId('rounds-3').getAttribute('aria-checked')).toBe('true');
		expect(screen.getByTestId('rounds-10').getAttribute('aria-checked')).toBe('false');
		expect(screen.getByTestId('expected-3').textContent).toBe('24');
		expect(screen.getByTestId('expected-10').textContent).toBe('80');
		expect(text()).toContain('expected counts, not evidence of completed work');
		expect(screen.getByTestId('cfg-run-type')).toBeTruthy();                        // the ORIGINAL run form
		expect(screen.queryByTestId('cfg10-submit')).toBeNull();
	});
	it('10 rounds: disabled FedProx/SecAgg are explained, the source mode is chosen explicitly, and the request carries exactly run_length and source_mode', async () => {
		const onStartTen = vi.fn();
		render(StudioRunStarter, { props: { capabilities: CAPS, onStartThree: vi.fn(), onStartTen } });
		await fireEvent.click(screen.getByTestId('rounds-10'));
		expect(screen.getByTestId('cfg10-algorithm').hasAttribute('disabled')).toBe(true);
		expect(screen.getByTestId('cfg10-algorithm-note').textContent).toContain('FedProx is disabled: not implemented or verified by the 10-round engine');
		expect(screen.getByTestId('cfg10-mode-note').textContent).toContain('SecAgg+ shadow is disabled');
		expect(screen.getByTestId('cfg10-mode-note').textContent).toContain('never silently reinterpreted');
		expect(screen.getByTestId('cfg10-source-note').textContent).toContain('Canonical synthetic cohort');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC' });
		await fireEvent.change(screen.getByTestId('cfg10-source'), { target: { value: 'LIVE_MONITORED_SITE_00' } });
		expect(screen.getByTestId('cfg10-source-note').textContent).toContain('NOT real patient physiology');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'LIVE_MONITORED_SITE_00' });
	});
	it('a live-monitored site can be chosen from the eight canonical sites; SITE_00 stays the unchanged default request', async () => {
		const sites = Array.from({ length: 8 }, (_, i) => ({ index: i, client_id: `SIM_FL_SITE_0${i}`, label: `SITE_0${i}`, profile: i === 3 ? 'sensor dropout' : 'clean signal' }));
		const onStartTen = vi.fn();
		render(StudioRunStarter, { props: { capabilities: { ...CAPS, ten_round: { ...CAPS.ten_round, monitored_sites: sites } } as StudioCapabilities, onStartThree: vi.fn(), onStartTen } });
		await fireEvent.click(screen.getByTestId('rounds-10'));
		expect(screen.queryByTestId('cfg10-site')).toBeNull();                        // only meaningful for the live-monitored source
		await fireEvent.change(screen.getByTestId('cfg10-source'), { target: { value: 'LIVE_MONITORED_SITE_00' } });
		const select = screen.getByTestId('cfg10-site') as HTMLSelectElement;
		expect([...select.options].map((o) => o.textContent)).toContain('SITE_03 — sensor dropout');
		expect(screen.getByTestId('cfg10-source-note').textContent).toContain('SITE_00');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'LIVE_MONITORED_SITE_00' });
		await fireEvent.change(select, { target: { value: '3' } });
		expect(screen.getByTestId('cfg10-source-note').textContent).toContain('SITE_03');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'LIVE_MONITORED_SITE_00', monitored_site: 3 });
	});
	it('MY MONITORING SESSION is a Training-data choice (not a source-mode detail): completed sessions only, fills SITE_00, labels stated', async () => {
		const store = getProductStore();
		store.sessions = [{ session_id: 'SESS-DONE-0123456789', state: 'COMPLETED', created_at_us: 1_700_000_000_000_000, simulation_provenance: { scenario_id: 'MIXED_MONITORING_SESSION', seed: 1, simulation_version: 'v' } }, { session_id: 'SESS-RUN', state: 'RUNNING', simulation_provenance: { scenario_id: 'NORMAL_MONITORING', seed: 2, simulation_version: 'v' } }] as never;
		vi.spyOn(store, 'loadSessions').mockResolvedValue(undefined);
		const sites = Array.from({ length: 8 }, (_, i) => ({ index: i, client_id: `SIM_FL_SITE_0${i}`, label: `SITE_0${i}`, profile: 'clean signal' }));
		const onStartTen = vi.fn();
		render(StudioRunStarter, { props: { capabilities: { ...CAPS, ten_round: { ...CAPS.ten_round, monitored_sites: sites } } as StudioCapabilities, onStartThree: vi.fn(), onStartTen } });
		await fireEvent.click(screen.getByTestId('rounds-10'));
		expect(screen.getByTestId('data-source-session').getAttribute('aria-checked')).toBe('false');
		expect(screen.queryByTestId('cfg10-session')).toBeNull();
		await fireEvent.click(screen.getByTestId('data-source-session'));
		expect(screen.getByTestId('data-source-session').getAttribute('aria-checked')).toBe('true');
		const pick = screen.getByTestId('cfg10-session') as HTMLSelectElement;
		expect([...pick.options].map((o) => o.value)).toEqual(['SESS-DONE-0123456789']);       // only COMPLETED sessions of a frozen scenario
		expect(pick.options[0].textContent).toContain('MIXED_MONITORING_SESSION');            // scenario first, shortened id, date: readable, not a bare id
		expect(screen.queryByTestId('cfg10-source')).toBeNull();                               // no source-mode / signal / replaced-client detail for this choice
		expect(screen.queryByTestId('cfg10-signal')).toBeNull();
		expect(screen.queryByTestId('cfg10-site')).toBeNull();
		expect(screen.getByTestId('cfg10-source-note').textContent).toMatch(/SITE_00.*synthetic-assigned.*recorded hardware/);
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'LIVE_MONITORED_SITE_00', signal_session_id: 'SESS-DONE-0123456789' });
	});
	it('a monitoring session cannot be combined with the untrained 3-round product form (it says why and blocks)', async () => {
		const store = getProductStore();
		store.sessions = [{ session_id: 'SESS-DONE', state: 'COMPLETED', simulation_provenance: { scenario_id: 'NORMAL_MONITORING', seed: 1, simulation_version: 'v' } }] as never;
		vi.spyOn(store, 'loadSessions').mockResolvedValue(undefined);
		const caps = { ...CAPS, ten_round: { ...CAPS.ten_round, initialisations: [{ id: 'FL_INIT_V2', label: 'u', default: false }, { id: 'MODEL_V2_FINAL', label: 'p', default: true }], rounds_by_initialisation: { FL_INIT_V2: [10], MODEL_V2_FINAL: [3, 10] }, default_initialisation: 'MODEL_V2_FINAL' } } as StudioCapabilities;
		render(StudioRunStarter, { props: { capabilities: caps, onStartThree: vi.fn(), onStartTen: vi.fn() } });
		await fireEvent.click(screen.getByTestId('data-source-session'));
		expect(screen.queryByTestId('session-needs-v2')).toBeNull();                          // pretrained start, 3 rounds: supported
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'FL_INIT_V2' } });
		expect(screen.getByTestId('session-needs-v2')).toBeTruthy();
		expect((screen.getByTestId('cfg10-submit') as HTMLButtonElement).disabled).toBe(true);
	});
	it('enables and transmits FedProx plus the verified round-one shadow only when the backend advertises both', async () => {
		const onStartTen = vi.fn();
		const supported = { ...CAPS, ten_round: { ...CAPS.ten_round, algorithms: ['FEDAVG', 'FEDPROX'], aggregation_modes: ['PLAIN', 'SECAGG_SHADOW'], unsupported: {} } };
		render(StudioRunStarter, { props: { capabilities: supported, onStartThree: vi.fn(), onStartTen } });
		await fireEvent.click(screen.getByTestId('rounds-10'));
		expect(screen.getByTestId('cfg10-algorithm').hasAttribute('disabled')).toBe(false);
		expect(screen.getByTestId('cfg10-mode').hasAttribute('disabled')).toBe(false);
		await fireEvent.change(screen.getByTestId('cfg10-algorithm'), { target: { value: 'FEDPROX' } });
		await fireEvent.change(screen.getByTestId('cfg10-mode'), { target: { value: 'SECAGG_SHADOW' } });
		expect(screen.getByTestId('cfg10-algorithm-note').textContent).toContain('current round-start global weights');
		expect(screen.getByTestId('cfg10-mode-note').textContent).toContain('authoritative plain aggregate');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', algorithm: 'FEDPROX', secagg_mode: 'SECAGG_SHADOW' });
	});
	it('10 rounds is disabled with an explanation when the backend lacks the engine, and while another run is active', async () => {
		render(StudioRunStarter, { props: { capabilities: null, onStartThree: vi.fn(), onStartTen: vi.fn() } });
		expect(screen.getByTestId('rounds-10').hasAttribute('disabled')).toBe(true);
		expect(screen.getByTestId('ten-unavailable').textContent).toContain('3-round default is unaffected');
		cleanup();
		const onStartTen = vi.fn();
		render(StudioRunStarter, { props: { capabilities: CAPS, liveBlocked: true, onStartThree: vi.fn(), onStartTen } });
		await fireEvent.click(screen.getByTestId('rounds-10'));
		expect(screen.getByTestId('cfg10-submit').hasAttribute('disabled')).toBe(true);
		expect(text()).toContain('ONE LIVE FEDERATION RUN AT A TIME');
	});
	it('arrow keys move between the two options (radio group)', async () => {
		render(StudioRunStarter, { props: { capabilities: CAPS, onStartThree: vi.fn(), onStartTen: vi.fn() } });
		await fireEvent.keyDown(screen.getByTestId('rounds-3'), { key: 'ArrowRight' });
		expect(screen.getByTestId('rounds-10').getAttribute('aria-checked')).toBe('true');
	});
});

function storeWith(over: (s: StudioStore) => void): StudioStore {
	const s = new StudioStore(() => ({} as unknown as ProductClient));
	over(s);
	return s;
}

describe('selected-round metric cards never invent values', () => {
	it('shows no metric labels until the evaluation state is known, and an explicit message for a run without evaluation', () => {
		render(MetricCards, { props: { studio: storeWith(() => undefined) } });
		expect(screen.getByTestId('evaluation-loading')).toBeTruthy();
		expect(text()).not.toMatch(/AUPRC|AUROC|F1|BCE/);
		cleanup();
		render(MetricCards, { props: { studio: storeWith((s) => { s.run = run({ evaluation: { available: false, source: 'LIVE', evaluation_run_id: 'x', reason: 'RUN_PREDATES_LIVE_EVALUATION', revision: 0 } }); }) } });
		expect(screen.getByTestId('no-evaluation').textContent).toContain('RUN_PREDATES_LIVE_EVALUATION');
		expect(text()).not.toMatch(/AUPRC|AUROC|BCE/);
	});
	it('a pending live round says so and the latest evaluated round is shown under an explicit label', () => {
		const s = storeWith((st) => { st.run = run(); st.summary = summary([record(0, 'COMPLETED'), record(1, 'COMPLETED'), record(2, 'EVALUATING'), record(3, 'QUEUED')]); st.executingRound = 3; st.latestCommittedRound = 3; });
		render(MetricCards, { props: { studio: s } });
		expect(s.selectedRound).toBe(3);
		expect(screen.getByTestId('metric-substitution').textContent).toContain('ROUND 3 EVALUATION QUEUED — showing the latest evaluated round R1');
		expect(screen.getByTestId('metric-round').textContent).toContain('ROUND R1');
		expect(screen.getByTestId('metric-AUPRC').textContent).toContain('0.911570');
	});
	it('a selected pending round shows pending text in every card (no zero, no copy of another round)', () => {
		const s = storeWith((st) => { st.run = run(); st.summary = summary([record(0, 'COMPLETED'), record(1, 'QUEUED')]); st.selectRound(1); });
		s.followLive = false;
		render(MetricCards, { props: { studio: s } });
		expect(screen.getByTestId('metric-status').textContent).toBe('QUEUED');
		for (const key of ['AUPRC', 'AUROC', 'F1', 'specificity', 'recall', 'accuracy', 'BCE', 'Brier']) expect(screen.getByTestId(`metric-${key}`).textContent).toContain('QUEUED');
		expect(screen.queryByTestId('metric-substitution')).toBeNull();
	});
	it('shows measured values, the undefined reason, the fixed rule, and the mandated reuse label; failures are alerts', () => {
		const s = storeWith((st) => { st.run = run({ status: 'COMPLETED', phase: 'DONE' }); st.summary = summary([record(0, 'COMPLETED'), record(1, 'FAILED')]); st.followLive = false; st.manualRound = 0; });
		render(MetricCards, { props: { studio: s } });
		expect(screen.getByTestId('metric-F1').textContent).toContain('0.350257');
		expect(screen.getByTestId('metric-specificity').textContent).toBe('Specificity0');
		expect(screen.getByTestId('all-negative_predictive_value').textContent).toContain('UNDEFINED — no negative predictions (TN+FN = 0)');
		expect(screen.getByTestId('cohort-use-label').textContent).toBe('REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST');
		expect(text()).toContain('raw sigmoid ≥ 0.5');
		cleanup();
		const failed = storeWith((st) => { st.run = run(); st.summary = summary([record(0, 'COMPLETED'), record(1, 'FAILED')]); st.followLive = false; st.manualRound = 1; });
		render(MetricCards, { props: { studio: failed } });
		expect(screen.getByRole('alert').textContent).toContain('EVALUATION FAILED — X: boom');
		expect(screen.getByTestId('metric-AUPRC').textContent).toContain('FAILED');
	});
});

describe('shared selected metric', () => {
	it('activating a metric card selects it for the whole page (the comparison follows it)', async () => {
		const s = storeWith((st) => { st.run = run(); st.summary = summary([record(0, 'COMPLETED'), record(1, 'COMPLETED')]); st.followLive = false; st.manualRound = 0; });
		render(MetricCards, { props: { studio: s } });
		expect(s.selectedMetric).toBe('AUPRC');
		await fireEvent.click(screen.getByTestId('metric-BCE'));
		expect(s.selectedMetric).toBe('BCE');
		expect(screen.getByTestId('metric-BCE').getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByTestId('metric-AUPRC').getAttribute('aria-pressed')).toBe('false');
	});
});

describe('run status strip, tabs and the owner-bound star', () => {
	function liveView(n: number) {
		const model = new FederationLiveModel(RUN_ID);
		for (const e of eventStream().slice(0, n)) model.applyRaw(e);
		return JSON.parse(JSON.stringify(model.snapshot));
	}
	it('shows actual accepted updates against the expected total and selectable committed rounds', async () => {
		const s = storeWith((st) => { st.run = run({ run_length: 3, planned_rounds: 3, run_id: RUN_ID }); st.summary = summary([record(0, 'COMPLETED', {}, RUN_ID), record(1, 'QUEUED', {}, RUN_ID)]); });
		const v = liveView(110);       // part-way through round 2
		render(RunStatusStrip, { props: { studio: s, view: v } });
		expect(screen.getByTestId('accepted-counter').textContent).toBe(`${v.submittedCount}/24`);
		expect(v.submittedCount).toBeGreaterThan(8);
		expect(screen.getByTestId('run-status-line').textContent).toContain('RUNNING');
		expect(screen.getByTestId('dot-R3').hasAttribute('disabled')).toBe(true);        // not started: not selectable
		await fireEvent.click(screen.getByTestId('dot-R1'));
		expect(s.followLive).toBe(false);
		expect(s.selectedRound).toBe(1);
	});
	it('analysis tabs are a keyboard-operable tablist and explain a run without captured data', async () => {
		const s = storeWith((st) => { st.run = run({ evaluation: { available: false, source: 'LIVE', evaluation_run_id: 'x', reason: 'RUN_PREDATES_LIVE_EVALUATION', revision: 0 } }); });
		render(AnalysisTabs, { props: { studio: s } });
		expect(screen.getAllByRole('tab')).toHaveLength(8);        // OVERVIEW … COMPARISON, GENERALISATION, FIGURES & EXPORTS
		expect(screen.getByTestId('atab-overview').getAttribute('aria-selected')).toBe('true');
		await fireEvent.keyDown(screen.getByTestId('atab-overview'), { key: 'ArrowRight' });
		expect(s.analysisTab).toBe('performance');
		expect(screen.getByTestId('analysis-unavailable').textContent).toContain('No per-round evaluation');
	});
	it('the ★ MY EDGE CLIENT presentation follows the unchanged owner-binding rule for every run kind', () => {
		expect(ownerBoundClientId('CLERK', 'LIVE_RUN')).toBe('SIM_FL_SITE_00');        // 3- and 10-round live runs under connected auth
		expect(ownerBoundClientId('DEMO', 'LIVE_RUN')).toBeNull();                      // DemoAuth must never show an authenticated owner
		expect(ownerBoundClientId('CLERK', 'REPLAY')).toBeNull();                       // replays and recorded evidence have no owner-bound client
		expect(ownerBoundClientId('CLERK', null)).toBeNull();
		const model = new FederationLiveModel(RUN_ID);
		for (const e of eventStream().slice(0, 30)) model.applyRaw(e);
		const clients = model.snapshot.clients;
		render(ClientGrid, { props: { live: clients, round: 1, replay: false, ownerBoundClientId: ownerBoundClientId('CLERK', 'LIVE_RUN'), selected: null, runDone: false } });
		expect(screen.getAllByTestId('owner-card-label')).toHaveLength(1);
		expect(screen.getByTestId('owner-card-label').textContent).toBe('★ MY EDGE CLIENT');
		expect(screen.getAllByTestId('peer-label')).toHaveLength(7);
		cleanup();
		render(ClientGrid, { props: { live: clients, round: 1, replay: false, ownerBoundClientId: ownerBoundClientId('DEMO', 'LIVE_RUN'), selected: null, runDone: false } });
		expect(screen.queryByTestId('owner-card-label')).toBeNull();
		expect(screen.queryByTestId('peer-label')).toBeNull();
	});
});
