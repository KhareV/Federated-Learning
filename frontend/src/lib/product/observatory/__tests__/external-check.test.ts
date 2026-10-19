// @vitest-environment jsdom
// The Observatory's external-check page: a strict parser of the hash-verified evidence, and the page that shows it with its boundaries.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Page from '../../../../routes/app/observatory/external-check/+page.svelte';
import { FrontendAuth } from '../../auth';
import { ProductStore, setProductStore } from '../../state.svelte';
import { FakeSocket, fakeBackend } from '../../__tests__/support';
import { parseExternalCheck } from '../external-check';

const row = (model: string, o: Record<string, unknown> = {}) => ({ model, AUROC: 0.911, AUROC_ci: [0.896, 0.926], AUPRC: 0.705, AUPRC_ci: [0.665, 0.743], lift: 6.4, F1: 0.547, F1_ci: [0.515, 0.579], sensitivity: 0.83, specificity: 0.85, precision: 0.45, paired_vs_central_V2: null, ...o });
const paired = (a: number, b: number) => ({ AUROC: { delta: a, ci95: [a - 0.02, a + 0.02], share_better: 0 }, AUPRC: { delta: b, ci95: [b - 0.03, b + 0.03], share_better: 0 } });
const MODELS = ['MODEL_V1 (central, frozen)', 'MODEL_V2_FINAL (central)', 'central V2 + 10 rounds on the original synthetic cohort', 'central V2 + 10 rounds on the realistic synthetic cohort'];
const SAMPLE = () => ({
	classification: 'FROZEN_EXTENSION_EVIDENCE', label: 'FROZEN EXTENSION EVIDENCE · REAL UNSEEN ECG · RECORD-LEVEL TARGET · NOT AAMI-SVF · NOT CLINICAL', claim_boundary: 'Extension outside the locked scope; no clinical claim.',
	target: 'PTBXL_PREMATURE_BEAT_RECORD_V1', records_scored: 21535, exclusions: { paced: 302, no_lead_II: 0, bad_window: 0 }, threshold: 0.5, calibration: 'NONE',
	report: { path: 'reports/ptbxl/external_check_v1.json', sha256: 'ab'.repeat(32) }, protocol: { path: 'docs/ptbxl/PTBXL_EXTERNAL_CHECK_V1.md', sha256: 'cd'.repeat(32), verified: true }, models: MODELS,
	sets: [{ name: 'primary (folds 9-10)', records: 4336, positives: 476, patients: 3809, prevalence: 0.1098, bootstrap_replicates: 2000, rows: [row(MODELS[0], { AUROC: 0.701, paired_vs_central_V2: paired(-0.21, -0.389) }), row(MODELS[1]), row(MODELS[2], { AUROC: 0.875, paired_vs_central_V2: paired(-0.036, -0.169) }), row(MODELS[3], { AUROC: 0.865, paired_vs_central_V2: paired(-0.046, -0.229) })] },
		{ name: 'replication (folds 1-8)', records: 17199, positives: 1893, patients: 14861, prevalence: 0.11, bootstrap_replicates: 2000, rows: MODELS.map((m) => row(m, { AUROC: 0.8 })) }],
	label_rules: [{ rule: 'rule A', title: 'A · union of the two label sources (primary)', records: 4336, positives: 476, rows: MODELS.map((m) => ({ model: m, AUROC: 0.9, AUPRC: 0.7, lift: 6 })) }],
	error_analysis: [{ group: 'negatives', records: 3860, share_flagged: 0.15 }, { group: 'negatives with AFIB', records: 236, share_flagged: 0.74 }], label_agreement: { both: 1052, statement_only: 472, extra_beats_only: 902 },
	limitations: ['One population: one external check.'] });

describe('the external-check parser', () => {
	it('accepts the backend view and keeps every shown value as read', () => {
		const v = parseExternalCheck(SAMPLE());
		expect(v.sets[0].rows[0].paired_vs_central_V2?.AUROC.delta).toBe(-0.21);
		expect(v.sets[0].rows[1].paired_vs_central_V2).toBeNull();
		expect(v.protocol.verified).toBe(true);
	});
	it('refuses an unverified protocol, a wrong classification, a missing field and a non-finite number', () => {
		expect(() => parseExternalCheck({ ...SAMPLE(), protocol: { ...SAMPLE().protocol, verified: false } })).toThrow('MALFORMED_EXTERNAL_CHECK_EVIDENCE');
		expect(() => parseExternalCheck({ ...SAMPLE(), classification: 'SOMETHING_ELSE' })).toThrow();
		const missing = SAMPLE() as Record<string, unknown>; delete missing.label_rules;
		expect(() => parseExternalCheck(missing)).toThrow();
		const nan = SAMPLE(); nan.sets[0].rows[0].AUROC = Number.NaN;
		expect(() => parseExternalCheck(nan)).toThrow();
	});
});

let backendPromise: () => Promise<unknown>;
beforeEach(() => {
	FakeSocket.reset();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	backendPromise = () => Promise.resolve(parseExternalCheck(SAMPLE()));
	const backend = Object.assign(fakeBackend(), { observatoryExternalCheck: () => backendPromise() });
	setProductStore(new ProductStore(new FrontendAuth({ createClient: () => backend }), (cb: () => void) => { cb(); return 0; }, (u) => new FakeSocket(u)));
});
afterEach(() => { cleanup(); setProductStore(null); vi.unstubAllGlobals(); });

describe('the external-check page', () => {
	it('states its boundaries first, then shows the models, the label rules and the error analysis from the evidence', async () => {
		render(Page);
		await waitFor(() => expect(screen.getByTestId('external-models')).toBeTruthy());
		expect(screen.getByTestId('extension-label').textContent).toContain('NOT AAMI-SVF');
		expect(screen.getByTestId('claim-boundary').textContent).toContain('no clinical claim');
		expect(document.body.textContent).toContain('removed from the project\'s execution scope');
		const rows = [...document.querySelectorAll('[data-testid="external-models"] tbody tr')];
		expect(rows.map((r) => r.getAttribute('data-model'))).toEqual(MODELS);
		expect(rows[0].textContent).toContain('−0.210');                                          // V1's paired change, read from the evidence
		expect(rows[1].textContent).toContain('reference');
		expect(screen.getByTestId('readings').textContent).toContain('clearly better than V1');
		expect(screen.getByTestId('readings').textContent).toContain('lowers its performance on this unseen real ECG');
		expect(screen.getByTestId('label-rules').textContent).toContain('1,052 both');
		expect(screen.getByTestId('error-analysis').textContent).toContain('74 %');
		expect(screen.getByTestId('hashes').textContent).toContain('abababababababab');
	});
	it('switches between the primary and the replication set', async () => {
		render(Page);
		await waitFor(() => expect(screen.getByTestId('external-models')).toBeTruthy());
		expect(screen.getByTestId('external-models').textContent).toContain('4,336 records');
		await fireEvent.click(screen.getByTestId('set-1'));
		expect(screen.getByTestId('external-models').textContent).toContain('17,199 records');
		expect(screen.getByTestId('set-1').getAttribute('aria-pressed')).toBe('true');
	});
	it('shows the failure instead of numbers when the evidence is unavailable', async () => {
		backendPromise = () => Promise.reject(new Error('EXTERNAL_CHECK_UNAVAILABLE:EXTERNAL_CHECK_PROTOCOL_HASH_MISMATCH'));
		render(Page);
		await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('PROTOCOL_HASH_MISMATCH'));
		expect(screen.queryByTestId('external-models')).toBeNull();
	});
});

describe('the dataset is named where the Observatory points to the check', () => {
	it('names PTB-XL in the Observatory navigation, the outcomes page and the page itself', async () => {
		const { readFileSync } = await import('node:fs');
		const { join } = await import('node:path');
		const read = (rel: string) => readFileSync(join(__dirname, '../../../../routes/app/observatory', rel), 'utf8');
		expect(read('+page.svelte')).toContain('External check on real PTB-XL ECG');
		expect(read('outcomes/+page.svelte')).toContain('External check on real PTB-XL ECG');
		expect(read('external-check/+page.svelte')).toContain('PTB-XL');
	});
});
