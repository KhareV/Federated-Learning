// @vitest-environment jsdom
// Generalisation lane: strict parsing, honest pending/failed display, frozen-V2 reference line, paired difference, and run isolation.
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it } from 'vitest';
import GeneralisationPanel from '$lib/components/product/studio/GeneralisationPanel.svelte';
import { fakeBackend } from '../../__tests__/support';
import { parseGeneralisation, StudioParseError } from '../parse';
import { StudioStore } from '../store.svelte';
import type { GenPair, GenRecord, GenRound, Generalisation } from '../types';
import { METRICS, digest, run } from './fixtures';

afterEach(() => cleanup());
const text = () => document.body.textContent ?? '';
const RUN = 'FL10RUN-GEN';
const G1_LABEL = 'UNSEEN SYNTHETIC COHORT — NOT USED FOR TRAINING, ROUND OR THRESHOLD SELECTION';
const V2 = { ...METRICS, AUPRC: 0.5, AUROC: 0.6, BCE: 0.9, Brier: 0.3, specificity: 0.8 };

function rec(round: number, status: GenRecord['evaluation_status'], over: Partial<GenRecord> = {}, subject: GenRecord['subject'] = 'FL_ROUND', metrics = METRICS): GenRecord {
	const done = status === 'COMPLETED';
	return { run_id: subject === 'FROZEN_V2_BASELINE' ? 'V2FROZEN-BASELINE' : RUN, run_length: subject === 'FROZEN_V2_BASELINE' ? 0 : 10, round_id: round, global_state_digest: digest(round + 1), candidate_id: null, cohort_id: 'WEARABLE_SIM_STUDIO_G1_UNSEEN_V1',
		cohort_use: G1_LABEL, evaluation_protocol_id: 'P', evaluation_status: status, evaluation_queued_at: 't0', evaluation_started_at: 't1', evaluation_completed_at: done ? 't2' : null, failure: status === 'FAILED' ? { code: 'X', message: 'boom' } : null,
		threshold: 0.5, calibration: 'NONE', windows: done ? 1446 : null, metric_result: done ? { ...metrics } : null, confusion_counts: done ? { TP: 280, FP: 200, TN: 939, FN: 27, predicted_positives: 480, predicted_negatives: 966 } : null, subject, ...over };
}
function pair(diff: number): GenPair {
	const m = { A_point: 0.5, B_point: 0.5 + diff, difference_point: diff, difference_interval: { lower: diff - 0.05, upper: diff + 0.05, valid_replicates: 2000 }, invalid_replicates: 0 };
	return { clusters: 16, replicates: 2000, seed: 20261201, method: 'paired participant-cluster percentile bootstrap', multiplicity: 'none; no significance claim', identical_predictions: diff === 0, metrics: Object.fromEntries(['AUPRC', 'AUROC', 'F1', 'accuracy', 'balanced_accuracy', 'recall', 'specificity', 'precision', 'BCE', 'Brier'].map((k) => [k, m])) };
}
export function gen(over: Partial<Generalisation> = {}, rounds?: GenRound[]): Generalisation {
	const rs: GenRound[] = rounds ?? [
		{ round_id: 0, record: rec(0, 'COMPLETED', {}, 'FL_ROUND', V2), paired_vs_v2: pair(0) },
		{ round_id: 1, record: rec(1, 'COMPLETED', {}, 'FL_ROUND', { ...METRICS, AUPRC: 0.62 }), paired_vs_v2: pair(0.12) },
		{ round_id: 2, record: rec(2, 'EVALUATING'), paired_vs_v2: null },
		{ round_id: 3, record: null, paired_vs_v2: null }];
	return { schema_version: 'STUDIO_GENERALISATION_V1', run_id: RUN, run_length: 3, observer_id: 'NHM_STUDIO_GENERALISATION_OBSERVER_V1', claim_boundary: 'SYNTHETIC_ENGINEERING_EVENT_GENERALISATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL', threshold: 0.5, calibration: 'NONE',
		base_model: { model_id: 'MODEL_V2_FINAL', label: 'Pretrained MODEL_V2_FINAL fine-tuned by federated rounds' },
		cohort: { cohort_id: 'WEARABLE_SIM_STUDIO_G1_UNSEEN_V1', label: G1_LABEL, detail: 'disjoint from training and the earlier holdouts', participants: 16, windows: 1446, positive_windows: 302, participant_ids: ['SIM_P000401'], site_conditions: ['SIM_FL_SITE_00'], manifest_sha256: digest(9), separation: null, separation_note: 'computed on first build' },
		baseline: { label: 'FROZEN V2 (MODEL_V2_FINAL) — unchanged, zero-shot on this task', detail: 'transfer reference, not a like-for-like trained competitor.', record: rec(0, 'COMPLETED', {}, 'FROZEN_V2_BASELINE', V2), state_sha256: digest(1) },
		rounds: rs, integrity: { r0_digest_equals_frozen_v2: true, r0_predictions_equal_frozen_v2: true }, metrics_order: ['AUPRC', 'AUROC', 'F1', 'specificity', 'recall', 'BCE', 'Brier'], lower_is_better: ['BCE', 'Brier'],
		interpretation: ['R01 versus frozen V2 on the unseen cohort (fixed 0.5 threshold, no calibration):', 'AUPRC: round 0.620 vs V2 0.500 (+0.120, higher; favourable direction).'], revision: 4, ...over };
}
function panelStore(g: Generalisation | null, mut: (s: StudioStore) => void = () => {}) {
	const s = new StudioStore(() => fakeBackend());
	s.run = run({ run_id: RUN, run_length: 3, planned_rounds: 3, status: 'RUNNING' });
	s.generalisation = g;
	mut(s);
	return s;
}

describe('parseGeneralisation is fail-closed', () => {
	it('accepts the typed payload and keeps every number as sent', () => {
		const parsed = parseGeneralisation(JSON.parse(JSON.stringify(gen())));
		expect(parsed.rounds[1].record?.metric_result?.AUPRC).toBe(0.62);
		expect(parsed.rounds[1].paired_vs_v2?.metrics.AUPRC.difference_point).toBe(0.12);
		expect(parsed.baseline.record?.subject).toBe('FROZEN_V2_BASELINE');
	});
	it('rejects a foreign schema, a record of another run, a baseline posing as a round, and numbers on an unfinished round', () => {
		const raw = () => JSON.parse(JSON.stringify(gen()));
		const schema = raw(); schema.schema_version = 'OTHER';
		const foreign = raw(); foreign.rounds[0].record.run_id = 'FL10RUN-OTHER';
		const subject = raw(); subject.baseline.record.subject = 'FL_ROUND';
		const phantom = raw(); phantom.rounds[2].record.metric_result = { AUPRC: 0.9 };
		const nonfinite = raw(); nonfinite.rounds[0].record.metric_result.AUPRC = 'NaN';
		for (const bad of [schema, foreign, subject, phantom]) expect(() => parseGeneralisation(bad)).toThrow(StudioParseError);
		expect(() => parseGeneralisation(nonfinite)).not.toThrow();       // a string is passed through as text and displayed as such, never coerced into a number
	});
});

describe('GeneralisationPanel', () => {
	it('labels the cohort, the starting model and the target, and draws only measured points', () => {
		const s = panelStore(gen());
		render(GeneralisationPanel, { props: { studio: s } });
		expect(screen.getByTestId('generalisation-cohort-label').textContent).toBe(G1_LABEL);
		expect(screen.getByTestId('generalisation-base-model').textContent).toContain('MODEL_V2_FINAL');
		expect(screen.getByTestId('generalisation-target').textContent).toContain('not AAMI-SVF');
		expect(screen.getByTestId('generalisation-r0-identical').textContent).toContain('identical to frozen V2');
		expect(screen.getByTestId('generalisation-progress').textContent).toContain('2/4 rounds scored');
		expect(screen.getByTestId('gen-chart-metric-point-fl-0')).toBeTruthy();
		expect(screen.getByTestId('gen-chart-metric-point-fl-1')).toBeTruthy();
		expect(screen.queryByTestId('gen-chart-metric-point-fl-2')).toBeNull();            // EVALUATING: nothing drawn
		expect(screen.queryByTestId('gen-chart-metric-point-fl-3')).toBeNull();            // not yet submitted: nothing drawn
		expect(screen.getByTestId('gen-chart-metric-line-v2').getAttribute('stroke-dasharray')).toBeTruthy();   // frozen V2 is a dashed reference line
		expect(screen.getByTestId('gen-chart-diff-zero')).toBeTruthy();
		expect(screen.getByTestId('gen-chart-diff-band')).toBeTruthy();
	});
	it('follows the live run: a pending selected round shows the latest SCORED round under an explicit label, never a copy of another value as its own', () => {
		const s = panelStore(gen(), (st) => { st.executingRound = 3; st.latestCommittedRound = 3; });
		render(GeneralisationPanel, { props: { studio: s } });
		expect(s.selectedRound).toBe(3);
		expect(text()).toContain('Showing R1 (latest scored round; R3 is not scored yet)');
		expect(screen.getByTestId('generalisation-table').textContent).toContain('R1 against frozen V2');
	});
	it('a manual selection of a scored round shows that round and its difference to frozen V2 with the nominal interval', () => {
		const s = panelStore(gen(), (st) => { st.executingRound = 3; st.latestCommittedRound = 3; st.selectRound(1); });
		render(GeneralisationPanel, { props: { studio: s } });
		const row = screen.getByTestId('generalisation-row-AUPRC').textContent ?? '';
		expect(row).toContain('0.500000');            // V2 column uses the stored frozen-V2 record
		expect(row).toContain('0.620000');            // R1 column uses R1's own record
		expect(row).toContain('+0.1200');
		expect(row).toContain('[0.0700, 0.1700]');
		expect(text()).not.toContain('Showing R1 (latest scored');
		expect(screen.getByTestId('generalisation-cm-v2').textContent).toContain('280');
	});
	it('a selected pending round shows its status in the cards, not a number', () => {
		const s = panelStore(gen(), (st) => { st.followLive = false; st.manualRound = 2; });
		render(GeneralisationPanel, { props: { studio: s } });
		expect(screen.getByTestId('generalisation-row-AUPRC').textContent).toContain('EVALUATING');
		expect(screen.getByTestId('generalisation-cm-fl').textContent).toContain('EVALUATING');
	});
	it('while frozen V2 is still being scored no comparison is shown, and a failed baseline is an alert', () => {
		const working = gen({ baseline: { ...gen().baseline, record: rec(0, 'EVALUATING', {}, 'FROZEN_V2_BASELINE') } });
		render(GeneralisationPanel, { props: { studio: panelStore(working) } });
		expect(screen.getByTestId('generalisation-baseline-working').textContent).toContain('nothing is estimated');
		cleanup();
		const failed = gen({ baseline: { ...gen().baseline, record: rec(0, 'FAILED', {}, 'FROZEN_V2_BASELINE') } });
		render(GeneralisationPanel, { props: { studio: panelStore(failed) } });
		expect(screen.getByRole('alert').textContent).toContain('Frozen V2 scoring failed');
	});
	it('an untrained start is described as such and frozen V2 as an external reference', () => {
		const g = gen({ base_model: { model_id: 'FL_INIT_V2', label: 'Untrained V2-architecture model (FL_INIT_V2) trained from scratch by federated rounds' }, integrity: { r0_digest_equals_frozen_v2: false, r0_predictions_equal_frozen_v2: false } });
		render(GeneralisationPanel, { props: { studio: panelStore(g) } });
		expect(screen.queryByTestId('generalisation-r0-identical')).toBeNull();
		expect(screen.getByTestId('generalisation-r0-different').textContent).toContain('external reference');
	});
	it('states the limits (G2 not executed, no selection/tuning) and makes no superiority claim', () => {
		render(GeneralisationPanel, { props: { studio: panelStore(gen()) } });
		const t = text();
		expect(t).toContain('was not executed');
		expect(t).toContain('Nothing here selects a round, tunes a threshold, calibrates, or promotes a model');
		expect(t).toContain('zero-shot transfer reference');
		expect(t.toLowerCase()).not.toMatch(/superior|outperform|clinically valid|better than/);
	});
	it('without data it says why (recorded runs) instead of inventing a panel', () => {
		render(GeneralisationPanel, { props: { studio: panelStore(null, (st) => { st.genNote = 'GENERALISATION_NOT_AVAILABLE: recorded evidence runs keep their own recorded diagnostic evaluation'; }) } });
		expect(screen.getByTestId('generalisation-unavailable').textContent).toContain('GENERALISATION_NOT_AVAILABLE');
		expect(screen.queryByTestId('generalisation-table')).toBeNull();
	});
});

describe('store isolation', () => {
	it('switching run clears the generalisation lane so nothing bleeds between runs', () => {
		const s = panelStore(gen());
		s.genCurves = { 1: { run_id: RUN, round_id: 1, available: false } };
		s.track('FL10RUN-OTHER');
		expect(s.generalisation).toBeNull();
		expect(s.genCurves).toEqual({});
		expect(s.genNote).toBeNull();
	});
});
