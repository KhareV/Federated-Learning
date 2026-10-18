// @vitest-environment jsdom
// The synthetic-cohort option: ORIGINAL (the frozen cohort) stays the default and changes nothing; REALISTIC is an explicit choice that travels in the request,
// is refused where it cannot apply (3 untrained rounds use the frozen product contract; a History session regenerates the original cohort's site signal) and is described by the run context.
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
import StudioRunStarter from '$lib/components/product/studio/StudioRunStarter.svelte';
import { createProductClient } from '$lib/product/api';
import { hardwareV2Texts, runContext } from '$lib/product/federation/run-context';
import { parseCapabilities, parseStudioRun } from '../parse';
import type { StudioCapabilities } from '../types';
import { run } from './fixtures';

afterEach(() => cleanup());
const INITS = [{ id: 'FL_INIT_V2' as const, label: 'Untrained V2-architecture model (FL_INIT_V2)', default: false }, { id: 'MODEL_V2_FINAL' as const, label: 'Pretrained MODEL_V2_FINAL', default: true }];
const COHORTS = [
	{ id: 'ORIGINAL' as const, label: 'Original synthetic cohort (frozen)', description: 'The frozen NHM_FL10_001 cohort: scheduled synthetic events added to a regular rhythm.', client_ids: ['SIM_FL_SITE_00'], evaluation_cohort_id: 'WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1', cohort_use: 'REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST', claim_boundary: 'c', default: true },
	{ id: 'REALISTIC' as const, label: 'Realistic synthetic cohort', description: 'Variable rhythm, premature ectopic beats with pauses, motion artifacts and annotation-noisy labels.', client_ids: ['SIM_FL_SITE_00'], evaluation_cohort_id: 'WEARABLE_SIM_REALISTIC_EVAL_COHORT_V2', cohort_use: 'REALISTIC SYNTHETIC EVALUATION COHORT — DIAGNOSTIC, ANNOTATION-NOISY, NOT CLINICAL', claim_boundary: 'c', default: false }];
const CAPS: StudioCapabilities = { studio_id: 'S', run_lengths: [3, 10], default_run_length: 3,
	ten_round: { available: true, initialisations: INITS, rounds_by_initialisation: { FL_INIT_V2: [10], MODEL_V2_FINAL: [3, 10] }, default_initialisation: 'MODEL_V2_FINAL', source_modes: ['CANONICAL_SYNTHETIC', 'LIVE_MONITORED_SITE_00'],
		algorithms: ['FEDAVG'], aggregation_modes: ['PLAIN'], unsupported: {}, expected_updates: 80, cohorts: COHORTS },
	three_round: { available: true, expected_updates: 24 }, evaluation: { observer_id: 'O', protocol_id: 'P', threshold: 0.5, calibration: 'NONE', cohort_use: 'x', cohort_use_detail: 'd', claim_boundary: 'c' } };
const mount = (caps: StudioCapabilities | null = CAPS) => { const onStartThree = vi.fn(), onStartTen = vi.fn(); render(StudioRunStarter, { props: { capabilities: caps, onStartThree, onStartTen } }); return { onStartThree, onStartTen }; };

describe('cohort selector', () => {
	it('is not shown by a backend that does not offer the option, and the request is unchanged', async () => {
		const legacy = { ...CAPS, ten_round: { ...CAPS.ten_round, cohorts: undefined } } as StudioCapabilities;
		const { onStartTen } = mount(legacy);
		expect(screen.queryByTestId('cohort-realistic')).toBeNull();
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL' });
	});
	it('defaults to ORIGINAL and does not add a cohort to the request', async () => {
		const { onStartTen } = mount();
		expect(screen.getByTestId('cohort-original').getAttribute('aria-checked')).toBe('true');
		expect(screen.getByTestId('cohort-note').textContent).toContain('frozen NHM_FL10_001 cohort');
		await fireEvent.click(screen.getByTestId('rounds-10'));
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL' });
	});
	it('REALISTIC travels in the request for 10 rounds and for 3 rounds from the pretrained start', async () => {
		const { onStartTen } = mount();
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		expect(screen.getByTestId('cohort-realistic').getAttribute('aria-checked')).toBe('true');
		expect(screen.getByTestId('cohort-note').textContent).toContain('premature ectopic beats');
		expect(screen.getByTestId('cfg10-cohort').textContent).toBe('REALISTIC');
		expect(screen.getByTestId('cfg10-source-note').textContent).toContain('Realistic synthetic cohort');       // the source note no longer calls the clients frozen
		expect(screen.getByTestId('cfg10-source-note').textContent).not.toContain('frozen');
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 3, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL', cohort: 'REALISTIC' });
		await fireEvent.click(screen.getByTestId('rounds-10'));
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL', cohort: 'REALISTIC' });
	});
	it('3 untrained rounds use the frozen product contract (original cohort only): realistic says so and cannot be submitted', async () => {
		const { onStartTen, onStartThree } = mount();
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'FL_INIT_V2' } });
		expect(screen.getByTestId('cohort-needs-v2').textContent).toContain('original cohort only');
		expect((screen.getByTestId('cfg10-submit') as HTMLButtonElement).disabled).toBe(true);
		expect(screen.queryByTestId('cfg-run-type')).toBeNull();                       // the original frozen form is not offered for the realistic cohort
		await fireEvent.click(screen.getByTestId('cohort-original'));                   // back to the original cohort: the frozen form returns unchanged
		expect(screen.getByTestId('cfg-run-type')).toBeTruthy();
		expect(onStartTen).not.toHaveBeenCalled();
		expect(onStartThree).not.toHaveBeenCalled();
	});
	it('10 untrained rounds with the realistic cohort are allowed', async () => {
		const { onStartTen } = mount();
		await fireEvent.click(screen.getByTestId('cohort-realistic'));
		await fireEvent.click(screen.getByTestId('rounds-10'));
		await fireEvent.change(screen.getByTestId('cfg10-init'), { target: { value: 'FL_INIT_V2' } });
		expect(screen.queryByTestId('cohort-needs-v2')).toBeNull();
		await fireEvent.click(screen.getByTestId('cfg10-submit'));
		expect(onStartTen).toHaveBeenLastCalledWith({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'FL_INIT_V2', cohort: 'REALISTIC' });
	});
});

describe('parsing and run context', () => {
	const raw = JSON.parse(JSON.stringify(CAPS));
	it('parses the advertised cohorts and refuses an unknown one', () => {
		expect(parseCapabilities(raw).ten_round.cohorts?.map((c) => c.id)).toEqual(['ORIGINAL', 'REALISTIC']);
		const bad = JSON.parse(JSON.stringify(CAPS));
		bad.ten_round.cohorts[1].id = 'EXOTIC';
		expect(() => parseCapabilities(bad)).toThrow();
		expect(parseCapabilities({ ...raw, ten_round: { ...raw.ten_round, cohorts: undefined } }).ten_round.cohorts).toBeUndefined();
	});
	it('a run descriptor carries its cohort; older descriptors mean ORIGINAL; an unknown cohort is refused', () => {
		expect(parseStudioRun({ ...run(), cohort: 'REALISTIC', cohort_label: 'Realistic synthetic cohort' }).cohort).toBe('REALISTIC');
		expect(parseStudioRun(run()).cohort).toBeUndefined();
		expect(() => parseStudioRun({ ...run(), cohort: 'EXOTIC' })).toThrow();
	});
	it('the run context names the realistic cohort in the badge and the data sentence, and keeps the original wording otherwise', () => {
		const original = runContext(run());
		expect(original.cohort).toBe('ORIGINAL');
		expect(original.badge).not.toContain('REALISTIC');
		expect(original.dataSentence).toContain('Synthetic engineering data on eight logical clients');
		const realistic = runContext(run({ cohort: 'REALISTIC' }));
		expect(realistic.cohort).toBe('REALISTIC');
		expect(realistic.badge).toContain('REALISTIC');
		expect(realistic.dataSentence).toContain('Realistic synthetic ECG');
		expect(realistic.dataSentence).toContain('no real physiology');
	});
});

describe('the request that reaches the backend', () => {
	const capture = () => { const sent: { url: string; body: Record<string, unknown> }[] = []; const client = createProductClient({ fetchImpl: (async (url: string, init: RequestInit) => { sent.push({ url, body: JSON.parse(String(init.body)) }); return new Response('{}', { status: 200 }); }) as never }); return { sent, client }; };
	it('a realistic Studio run carries its cohort in the POST body (a field the client does not forward is silently lost)', async () => {
		const { sent, client } = capture();
		await client.studioStartTenRound({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL', cohort: 'REALISTIC' }).catch(() => undefined);
		expect(sent[0].url).toContain('/studio/runs');
		expect(sent[0].body).toEqual({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL', cohort: 'REALISTIC', algorithm: 'FEDAVG', secagg_mode: 'PLAIN' });
	});
	it('an original run sends no cohort key at all, exactly as before', async () => {
		const { sent, client } = capture();
		await client.studioStartTenRound({ run_length: 10, source_mode: 'CANONICAL_SYNTHETIC', initialisation: 'MODEL_V2_FINAL' }).catch(() => undefined);
		expect(sent[0].body).not.toHaveProperty('cohort');
	});
	it('a realistic recorded-hardware run carries its cohort in the POST body', async () => {
		const { sent, client } = capture();
		await client.hardwareDemoStart({ session_ids: ['HW-1'], run_length: 3, algorithm: 'FEDAVG', secagg_mode: 'PLAIN', label_seed: 1, initialisation: 'MODEL_V2_FINAL', cohort: 'REALISTIC' }).catch(() => undefined);
		expect(sent[0].url).toContain('/studio/hardware-demo/runs');
		expect(sent[0].body.cohort).toBe('REALISTIC');
	});
});

describe('wording of a pretrained-V2 recorded-hardware run follows its cohort', () => {
	it('the original cohort keeps the canonical / frozen wording exactly', () => {
		const t = hardwareV2Texts('ORIGINAL');
		expect(t.peers).toContain('canonical synthetic peers');
		expect(t.metricsNote).toContain('same frozen synthetic evaluation cohort');
		expect(t.metricsNote).toContain('comparable with a synthetic pretrained-V2 run');
	});
	it('the realistic cohort never calls its peers canonical or its holdout frozen', () => {
		const t = hardwareV2Texts('REALISTIC');
		expect(t.peers).toContain('realistic synthetic peers');
		expect(t.peers).not.toContain('canonical');
		expect(t.metricsNote).toContain('realistic synthetic evaluation cohort');
		expect(t.metricsNote).toContain('comparable with a realistic-cohort synthetic pretrained-V2 run');
		expect(t.metricsNote).not.toContain('frozen');
	});
});
