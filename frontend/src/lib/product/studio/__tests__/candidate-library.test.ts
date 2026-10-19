// @vitest-environment jsdom
// The candidate library in the UI: a stored engineering candidate can be chosen as the starting model of a synthetic, monitored-site or recorded-hardware run, travels in the request,
// is described on the run, and is listed (never promoted or deployed) on the Models page.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CandidateLibrary from '$lib/components/product/studio/CandidateLibrary.svelte';
import StudioRunStarter from '$lib/components/product/studio/StudioRunStarter.svelte';
import { createProductClient } from '$lib/product/api';
import { hardwareQualityText, runContext } from '$lib/product/federation/run-context';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FakeSocket, fakeBackend } from '../../__tests__/support';
import { parseCandidate, parseCandidates, parseCapabilities, parseStudioRun } from '../parse';
import type { StudioCapabilities } from '../types';
import { run } from './fixtures';

const immediate = (cb: () => void) => { cb(); return 0; };
const RAW = (over: Record<string, unknown> = {}) => ({
	schema_version: 'STUDIO_ENGINEERING_CANDIDATE_V1', candidate_id: 'FL10_CANDIDATE_FL10RUN-AAA', label: 'ENGINEERING CANDIDATE - NOT PROMOTED - NOT CLINICAL', created_at: '2026-10-18T12:00:00+00:00', source_run_id: 'FL10RUN-AAA',
	source_kind: 'SYNTHETIC_COHORT', source_detail: { source_mode: 'CANONICAL_SYNTHETIC' }, cohort: 'REALISTIC', cohort_label: 'Realistic synthetic cohort', evaluation_cohort_id: 'WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2', run_length: 10, round_id: 10,
	algorithm: 'FEDAVG', secagg_mode: 'PLAIN', base_model: { model_id: 'MODEL_V2_FINAL' }, state_sha256: 'ab'.repeat(32), metrics: { AUPRC: 0.8123, AUROC: 0.91, F1: 0.7 }, promoted: false, deployed: false, registered_in_product_registry: false, used_for_monitoring: false, ...over });
const CAND_ORIGINAL = RAW({ candidate_id: 'FL10_CANDIDATE_FL10RUN-BBB', cohort: 'ORIGINAL', cohort_label: 'Original synthetic cohort (frozen)', source_kind: 'RECORDED_HARDWARE', run_length: 3, metrics: null, base_model: { kind: 'CANDIDATE', model_id: 'FL10_CANDIDATE_FL10RUN-AAA' } });

afterEach(() => { cleanup(); setProductStore(null); });

describe('parsing', () => {
	it('parses a candidate and refuses one that claims to be promoted, deployed, registered or used for monitoring', () => {
		const c = parseCandidate(RAW());
		expect(c.cohort).toBe('REALISTIC');
		expect(c.metrics?.AUPRC).toBe(0.8123);
		for (const flag of ['promoted', 'deployed', 'registered_in_product_registry', 'used_for_monitoring']) expect(() => parseCandidate(RAW({ [flag]: true })), flag).toThrow();
		expect(() => parseCandidate(RAW({ cohort: 'EXOTIC' }))).toThrow();
		expect(parseCandidates([RAW(), CAND_ORIGINAL]).map((x) => x.candidate_id)).toEqual(['FL10_CANDIDATE_FL10RUN-AAA', 'FL10_CANDIDATE_FL10RUN-BBB']);
		expect(parseCandidate(CAND_ORIGINAL).metrics).toBeNull();
	});
	it('a run started from a candidate names the candidate as its base model; an unknown plain base model is still refused', () => {
		const started = parseStudioRun({ ...run(), base_model: { model_id: 'FL10_CANDIDATE_FL10RUN-AAA', kind: 'CANDIDATE', label: 'Engineering candidate', candidate_cohort: 'REALISTIC', source_run_id: 'FL10RUN-AAA', state_sha256: 'cd'.repeat(32) } });
		expect(started.base_model?.kind).toBe('CANDIDATE');
		expect(started.base_model?.candidate_cohort).toBe('REALISTIC');
		expect(() => parseStudioRun({ ...run(), base_model: { model_id: 'SOMETHING_ELSE', label: 'x' } })).toThrow();
	});
	it('capabilities advertise the library and the rounds a candidate start allows (outside the pinned initialisation map)', () => {
		const caps = { studio_id: 'S', run_lengths: [3, 10], default_run_length: 3, ten_round: { available: true, source_modes: ['CANONICAL_SYNTHETIC'], algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: {}, expected_updates: 80, rounds_by_initialisation: { MODEL_V2_FINAL: [3, 10] } },
			candidate_library: { available: true, count: 2, rounds: [3, 10], note: 'kept across restarts' }, three_round: { available: true, expected_updates: 24 }, evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'x', cohort_use_detail: 'd', claim_boundary: 'c' } };
		const parsed = parseCapabilities(caps);
		expect(parsed.candidate_library).toEqual({ available: true, count: 2, rounds: [3, 10], note: 'kept across restarts' });
		expect(parsed.ten_round.rounds_by_initialisation).toEqual({ MODEL_V2_FINAL: [3, 10] });          // the pinned initialisation contract is untouched
	});
});

describe('the request that reaches the backend', () => {
	const capture = () => { const sent: { url: string; method: string; body: Record<string, unknown> | null }[] = []; const client = createProductClient({ fetchImpl: (async (url: string, init: RequestInit) => { sent.push({ url, method: String(init.method), body: init.body ? JSON.parse(String(init.body)) : null }); return new Response(url.endsWith('/candidates') ? '[]' : '{}', { status: 200 }); }) as never }); return { sent, client }; };
	it('a Studio run started from a candidate carries initialisation and candidate_id (a field the client does not forward is silently lost)', async () => {
		const { sent, client } = capture();
		await client.studioStartTenRound({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'CANDIDATE', candidate_id: 'FL10_CANDIDATE_FL10RUN-AAA', cohort: 'REALISTIC' }).catch(() => undefined);
		expect(sent[0].body).toEqual({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'CANDIDATE', candidate_id: 'FL10_CANDIDATE_FL10RUN-AAA', cohort: 'REALISTIC', algorithm: 'FEDAVG', secagg_mode: 'PLAIN' });
	});
	it('a run that does not start from a candidate sends no candidate_id', async () => {
		const { sent, client } = capture();
		await client.studioStartTenRound({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL' }).catch(() => undefined);
		expect(sent[0].body).not.toHaveProperty('candidate_id');
	});
	it('a recorded-hardware run started from a candidate carries it; the library is read with GET /studio/candidates', async () => {
		const { sent, client } = capture();
		await client.hardwareDemoStart({ session_ids: ['HW-1'], run_length: 3, algorithm: 'FEDAVG', secagg_mode: 'PLAIN', label_seed: 1, initialisation: 'CANDIDATE', candidate_id: 'FL10_CANDIDATE_FL10RUN-AAA' }).catch(() => undefined);
		expect(sent[0].body?.candidate_id).toBe('FL10_CANDIDATE_FL10RUN-AAA');
		expect(await client.studioCandidates()).toEqual([]);
		expect(sent[1]).toMatchObject({ method: 'GET' });
		expect(sent[1].url).toMatch(/\/studio\/candidates$/);
	});
});

describe('run context', () => {
	const started = (over: Record<string, unknown> = {}) => run({ base_model: { model_id: 'FL10_CANDIDATE_FL10RUN-AAA', kind: 'CANDIDATE', label: 'c', candidate_cohort: 'REALISTIC', source_run_id: 'FL10RUN-AAA' }, ...over } as never);
	it('a candidate start keeps the pretrained-V2 family capabilities and names its candidate', () => {
		const ctx = runContext(started());
		expect(ctx.lineage).toBe('MODEL_V2_FINAL');
		expect(ctx.startCandidate).toEqual({ id: 'FL10_CANDIDATE_FL10RUN-AAA', cohort: 'REALISTIC', sourceRunId: 'FL10RUN-AAA' });
		expect(ctx.capabilities.generalisation.available).toBe(true);
	});
	it('a hardware run started from a candidate is a pretrained-V2-family hardware run', () => {
		const ctx = runContext(started({ engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE' }));
		expect(ctx.lineage).toBe('HARDWARE_V2_PRETRAINED');
		expect(ctx.clients).toBe('RECORDED_CLIENT_PLUS_SIM_PEERS');
	});
	it('a run that did not start from a candidate has none', () => {
		expect(runContext(run()).startCandidate).toBeNull();
	});
});

const CAPS = (count: number): StudioCapabilities => ({ studio_id: 'S', run_lengths: [3, 10], default_run_length: 3,
	ten_round: { available: true, initialisations: [{ id: 'FL_INIT_V2', label: 'u', default: false }, { id: 'MODEL_V2_FINAL', label: 'p', default: true }], rounds_by_initialisation: { FL_INIT_V2: [10], MODEL_V2_FINAL: [3, 10] }, default_initialisation: 'MODEL_V2_FINAL',
		source_modes: ['CANONICAL_SYNTHETIC'], algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: {}, expected_updates: 80,
		cohorts: [{ id: 'ORIGINAL', label: 'Original', description: 'frozen', client_ids: ['SIM_FL_SITE_00'], evaluation_cohort_id: 'E1', cohort_use: 'u', claim_boundary: 'c', default: true }, { id: 'REALISTIC', label: 'Realistic', description: 'premature ectopic beats', client_ids: ['SIM_FL_SITE_00'], evaluation_cohort_id: 'E2', cohort_use: 'u', claim_boundary: 'c', default: false }] },
	candidate_library: { available: true, count, rounds: [3, 10], note: 'n' }, three_round: { available: true, expected_updates: 24 },
	evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'x', cohort_use_detail: 'd', claim_boundary: 'c' } });

function install(candidates: unknown[]) {
	FakeSocket.reset();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = Object.assign(fakeBackend(), { studioCandidates: () => Promise.resolve(parseCandidates(candidates)) });
	setProductStore(new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u)));
}

describe('starting a synthetic run from a candidate', () => {
	beforeEach(() => install([RAW(), CAND_ORIGINAL]));
	const mount = (caps: StudioCapabilities) => { const onStartTen = vi.fn(); render(StudioRunStarter, { props: { capabilities: caps, onStartThree: vi.fn(), onStartTen } }); return { onStartTen }; };
	it('offers the library as a starting model, lists the candidates with their cohort, and sends the choice (3 rounds allowed)', async () => {
		const { onStartTen } = mount(CAPS(2));
		await waitFor(() => expect([...(screen.getByTestId('cfg10-init') as HTMLSelectElement).options].map((o) => o.value)).toContain('CANDIDATE'));
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'CANDIDATE' } });
		const picker = screen.getByTestId('cfg10-candidate') as HTMLSelectElement;
		expect([...picker.options].map((o) => o.value)).toEqual(['FL10_CANDIDATE_FL10RUN-BBB', 'FL10_CANDIDATE_FL10RUN-AAA']);
		expect([...picker.querySelectorAll('optgroup')].map((g) => g.label)).toEqual(['Trained on the original cohort', 'Trained on the realistic cohort (invented noise)']);      // segregated by the cohort each candidate was trained on
		expect(picker.options[1].textContent).toContain('AUPRC 0.812');
		await fireEvent.change(picker, { target: { value: 'FL10_CANDIDATE_FL10RUN-BBB' } });
		expect(screen.getByTestId('cfg10-candidate-note').textContent).toContain('recorded-hardware run on the original cohort');
		expect(screen.getByTestId('cfg10-init-note').textContent).toContain('R0 is the final state of the candidate chosen below');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));                               // 3 rounds from a candidate use the extended engine
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'CANDIDATE', candidate_id: 'FL10_CANDIDATE_FL10RUN-BBB' });
	});
	it('says so when the candidate was trained on the other cohort, and the realistic cohort accepts a candidate for 3 rounds', async () => {
		const { onStartTen } = mount(CAPS(2));
		await waitFor(() => expect([...(screen.getByTestId('cfg10-init') as HTMLSelectElement).options].map((o) => o.value)).toContain('CANDIDATE'));
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'CANDIDATE' } });
		expect(screen.getByTestId('cfg10-candidate-note').textContent).toContain('This run uses the original cohort');           // candidate AAA is realistic, the run is on the original cohort
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		expect(screen.getByTestId('cfg10-candidate-note').textContent).not.toContain('This run uses');
		expect(screen.queryByTestId('cohort-needs-v2')).toBeNull();
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'CANDIDATE', candidate_id: 'FL10_CANDIDATE_FL10RUN-AAA', cohort: 'REALISTIC' });
	});
	it('does not offer the candidate start when the library is empty', async () => {
		install([]);
		mount(CAPS(0));
		await new Promise((r) => setTimeout(r, 30));
		expect([...(screen.getByTestId('cfg10-init') as HTMLSelectElement).options].map((o) => o.value)).not.toContain('CANDIDATE');
	});
});

describe('the library panel', () => {
	it('lists each candidate with its cohort, source, scores and the not-promoted / not-deployed labels', async () => {
		install([RAW(), CAND_ORIGINAL]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getAllByTestId('library-candidates').length).toBe(2));          // one list per training cohort
		const cards = screen.getAllByRole('listitem').filter((li) => li.hasAttribute('data-candidate'));
		expect(cards.map((c) => c.getAttribute('data-cohort'))).toEqual(['ORIGINAL', 'REALISTIC']);
		expect(cards[1].textContent).toContain('0.812');
		expect(cards[0].textContent).toContain('NOT DEPLOYED');
		expect(cards[0].textContent).toContain('Recorded-hardware run');
		expect(cards[0].textContent).toContain('candidate FL10_CANDIDATE_FL10RUN-AAA');               // lineage: it started from the first candidate
		expect(cards[0].textContent).toContain('—');                                                   // no scores snapshot: shown as undefined, never as zero
	});
	it('explains the empty library', async () => {
		install([]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getByTestId('no-library-candidates').textContent).toContain('final engineering candidate'));
	});
});


describe('quality of the recorded windows in a pretrained-V2 hardware run', () => {
	const rq = (over: Record<string, unknown> = {}) => ({ recorded: true, windows: 73, VALID: 60, DEGRADED: 5, UNUSABLE: 8, accepted_below_valid: 13, ...over });
	it('is parsed from the run descriptor, with nulls kept as nulls', () => {
		expect(parseStudioRun({ ...run(), recorded_quality: rq() }).recorded_quality).toEqual({ recorded: true, windows: 73, VALID: 60, DEGRADED: 5, UNUSABLE: 8, accepted_below_valid: 13 });
		expect(parseStudioRun({ ...run(), recorded_quality: rq({ recorded: false, VALID: null, DEGRADED: null, UNUSABLE: null, accepted_below_valid: null }) }).recorded_quality).toEqual({ recorded: false, windows: 73, VALID: null, DEGRADED: null, UNUSABLE: null, accepted_below_valid: null });
		expect(parseStudioRun(run()).recorded_quality).toBeUndefined();
		expect(parseStudioRun({ ...run(), recorded_quality: null }).recorded_quality).toBeNull();
	});
	it('says how many windows are VALID and how many lower-quality windows were accepted for experimental training', () => {
		const text = hardwareQualityText(rq());
		expect(text).toContain('60 are graded VALID');
		expect(text).toContain('13 lower-quality windows (5 degraded, 8 unusable) were accepted for experimental training');
		expect(text).toContain('reported, not enforced');
		expect(hardwareQualityText(rq({ accepted_below_valid: 1, DEGRADED: 1, UNUSABLE: 0 }))).toContain('1 lower-quality window (1 degraded, 0 unusable) was accepted');
	});
	it('an older run whose grades were not kept says the split is unknown instead of showing numbers', () => {
		const text = hardwareQualityText({ recorded: false, windows: 73, VALID: null, DEGRADED: null, UNUSABLE: null, accepted_below_valid: null });
		expect(text).toContain('not kept for this older run');
		expect(text).toContain('unknown');
		expect(text).not.toMatch(/graded VALID/);
	});
});


describe('label provenance of a run is named for the clients that really have each kind', () => {
	const hist = (over: Record<string, unknown> = {}) => run({ source_mode: 'LIVE_MONITORED_SITE_00', monitored_site: 2, ...over } as never);
	it('a History-derived run has an assigned-label client plus event-label peers, not "engineering events" for everyone', () => {
		expect(runContext(hist({ signal_session_id: 'SES-1' })).labels).toBe('SYNTHETIC_ASSIGNED_CLIENT_PLUS_EVENT_PEERS');
		expect(runContext(hist({ signal_session_id: 'SES-1' })).dataSentence).toContain('synthetic-assigned labels');
	});
	it('a live-monitored site (no History session) and a plain synthetic run keep event-window labels', () => {
		expect(runContext(hist()).labels).toBe('SYNTHETIC_ENGINEERING_EVENTS');
		expect(runContext(run()).labels).toBe('SYNTHETIC_ENGINEERING_EVENTS');
	});
	it('a pretrained-V2 hardware run is assigned client plus event peers; the tabular hardware family is all assigned', () => {
		const v2 = run({ engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE', base_model: { model_id: 'MODEL_V2_FINAL', label: 'p' } } as never);
		const tabular = run({ engine: 'HARDWARE_DEMO', source_mode: 'RECORDED_HARDWARE', base_model: { model_id: 'HARDWARE_DEMO_MODEL_V1', label: 't' } } as never);
		expect(runContext(v2).labels).toBe('SYNTHETIC_ASSIGNED_CLIENT_PLUS_EVENT_PEERS');
		expect(runContext(tabular).labels).toBe('SYNTHETIC_ASSIGNED_FOR_DEMO');
	});
});


describe('the library groups candidates by the cohort they were trained on and shows their lineage', () => {
	it('separates candidates by training cohort, says scores on different evaluation cohorts are not comparable, and draws the lineage chain', async () => {
		const original = RAW({ candidate_id: 'FL10_CANDIDATE_FL10RUN-ORIG', cohort: 'ORIGINAL', evaluation_cohort_id: 'WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1', base_model: { model_id: 'MODEL_V2_FINAL' } });
		const child = RAW({ candidate_id: 'FL10_CANDIDATE_FL10RUN-CHILD', base_model: { kind: 'CANDIDATE', model_id: 'FL10_CANDIDATE_FL10RUN-AAA' } });
		install([RAW(), child, original]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getAllByTestId('library-group').length).toBe(2));
		expect(screen.getAllByTestId('library-group').map((g) => g.textContent)).toEqual(['Trained on the original cohort', 'Trained on the realistic cohort (invented noise)']);
		expect(screen.getByTestId('library-not-comparable').textContent).toContain('not comparable');
		const lineages = screen.getAllByTestId('library-lineage').map((l) => l.textContent);
		expect(lineages).toContain('Lineage: FL10_CANDIDATE_FL10RUN-CHILD ← FL10_CANDIDATE_FL10RUN-AAA ← MODEL_V2_FINAL');
		expect(lineages).toContain('Lineage: FL10_CANDIDATE_FL10RUN-ORIG ← MODEL_V2_FINAL');
	});
	it('says so when a parent candidate is no longer in the library, and shows no comparability warning for a single cohort', async () => {
		install([RAW({ candidate_id: 'FL10_CANDIDATE_FL10RUN-ORPHAN', base_model: { kind: 'CANDIDATE', model_id: 'FL10_CANDIDATE_GONE' } })]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getByTestId('library-lineage').textContent).toBe('Lineage: FL10_CANDIDATE_FL10RUN-ORPHAN ← FL10_CANDIDATE_GONE ← (not in this library)'));
		expect(screen.queryByTestId('library-not-comparable')).toBeNull();
	});
	it('cautions that adapting to the synthetic cohort lowered real-ECG performance, so a candidate is not a better ECG model', async () => {
		install([RAW()]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getByTestId('library-real-ecg-caution').textContent).toMatch(/lowered performance on real MIT-BIH validation ECG.*not a better ECG model/));
	});
});

const RESEARCH = RAW({ candidate_id: 'RESEARCH_FL_V2_FL001_R50', source_run_id: 'V2-FL-001', source_kind: 'RESEARCH_FEDERATED_CHECKPOINT', cohort: 'REAL_ECG', cohort_label: 'Real MIT-BIH training patients in 8 simulated sites (no synthetic cohort)',
	evaluation_cohort_id: 'MITBIH_OFFICIAL_VALIDATION (7 patient groups, 2,880 real windows; V2-FL-001 model selection used it)', run_length: 50, round_id: 50, base_model: { model_id: 'FL_INIT_V2', kind: 'RANDOM_INITIALISATION' }, metrics: { AUPRC: 0.8268, AUROC: 0.92, F1: 0.696 } });

describe('an imported federated research checkpoint (real MIT-BIH patients, no synthetic cohort)', () => {
	it('is parsed, and a record that claims a made-up cohort or source is still refused', () => {
		const [c] = parseCandidates([RESEARCH]);
		expect(c.cohort).toBe('REAL_ECG');
		expect(c.source_kind).toBe('RESEARCH_FEDERATED_CHECKPOINT');
		expect(() => parseCandidates([RAW({ cohort: 'MADE_UP' })])).toThrow();
		expect(() => parseCandidates([RAW({ source_kind: 'MADE_UP' })])).toThrow();
		expect(() => parseCandidates([{ ...RESEARCH, deployed: true }])).toThrow();                 // the never-deployed rule applies to it too
	});
	it('is listed as real ECG with no synthetic cohort, in its own score group, and never as an original-cohort candidate', async () => {
		install([RAW(), RESEARCH]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getAllByTestId('library-candidates').length).toBe(2));
		const card = screen.getAllByRole('listitem').find((li) => li.getAttribute('data-candidate') === 'RESEARCH_FL_V2_FL001_R50')!;
		expect(card.getAttribute('data-cohort')).toBe('REAL_ECG');
		expect(card.textContent).toContain('REAL ECG · NO SYNTHETIC COHORT');
		expect(card.textContent).not.toContain('ORIGINAL COHORT');
		expect(card.textContent).toContain('Imported federated research checkpoint');
		expect(card.textContent).toContain('NOT DEPLOYED');
		expect(screen.getAllByTestId('library-group').length).toBe(2);                              // its scores are on real validation windows, so not comparable with the synthetic-cohort candidate
		expect(screen.getByTestId('library-not-comparable').textContent).toContain('not comparable');
		expect(card.textContent).toContain('FL_INIT_V2');                                           // lineage: it started from a random V2 initialisation, not from the central checkpoint
	});
	it('reads as trained on real patients when chosen as the starting model, and always notes that the run uses a synthetic cohort', async () => {
		install([RESEARCH]);
		const onStartTen = vi.fn();
		render(StudioRunStarter, { props: { capabilities: CAPS(1), onStartThree: vi.fn(), onStartTen } });
		await waitFor(() => expect([...(screen.getByTestId('cfg10-init') as HTMLSelectElement).options].map((o) => o.value)).toContain('CANDIDATE'));
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'CANDIDATE' } });
		const note = screen.getByTestId('cfg10-candidate-note').textContent ?? '';
		expect(note).toContain('imported federated research checkpoint');
		expect(note).toContain('real MIT-BIH training patients in eight simulated sites (no synthetic cohort)');
		expect(note).not.toMatch(/on the original cohort\./);
		expect(note).toContain('This run uses the original cohort');
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		expect(screen.getByTestId('cfg10-candidate-note').textContent).toContain('This run uses the realistic cohort');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'CANDIDATE', candidate_id: 'RESEARCH_FL_V2_FL001_R50', cohort: 'REALISTIC' });
	});
});

describe('a candidate of the recorded-noise realistic cohort', () => {
	it('is listed with its own chip and option text, and parsed', async () => {
		const c = RAW({ candidate_id: 'FL10_CANDIDATE_FL10RUN-NSTDB', cohort: 'REALISTIC_NSTDB', cohort_label: 'Realistic cohort with recorded noise (NSTDB)', evaluation_cohort_id: 'WEARABLE_SIM_REALISTIC_EVAL_COHORT_V3' });
		expect(parseCandidates([c])[0].cohort).toBe('REALISTIC_NSTDB');
		install([c]);
		render(CandidateLibrary);
		await waitFor(() => expect(screen.getByTestId('library-cohort').textContent).toContain('RECORDED NOISE'));
		expect(screen.getByTestId('library-cohort').textContent).not.toContain('ORIGINAL');
	});
});

