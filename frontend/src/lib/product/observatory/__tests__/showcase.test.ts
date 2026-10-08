import { describe, expect, it } from 'vitest';
import { parseShowcase } from '../showcase';

const base = () => ({
	schema_version: 'NHM_FINAL_SHOWCASE_RESEARCH_BUNDLE_V1', lanes: { A: 'a', B: 'b', C: 'c', H: 'h' },
	datasets: { INCART: { claim_label: 'x', clusters: 1, windows: 1 } }, models: [], round_logs: {},
	comparability: { rows: [], checks: [], interpretations: [], verdict: 'DESCRIPTIVE' }, limitations: [], historical_centralized: { label: 'x' },
	synthetic: { boundary_label: 'SYNTHETIC', protocol_sha256: 'p', method_freeze_commit: 'm', candidate_digest: 'c', state_digests: { round_0: 'd' }, holdout_windows: 2, source: 's', sha256: 'h',
		states: { round_0: { pooled: { AUPRC: 0.5, precision: null }, undefined: { precision: 'no predicted positives' }, participant_macro_F1: null, uncertainty: {}, per_participant: {} } } }
});

describe('showcase bundle parser', () => {
	it('keeps undefined synthetic metrics as null rather than zero', () => {
		const parsed = parseShowcase(base());
		expect(parsed.synthetic?.states.round_0.pooled.precision).toBeNull();
		expect(parsed.synthetic?.states.round_0.participant_macro_F1).toBeNull();
		expect(parsed.synthetic?.states.round_0.undefined.precision).toContain('no predicted');
	});
	it('fails closed on a wrong schema, non-finite numbers and malformed rows', () => {
		expect(() => parseShowcase({ ...base(), schema_version: 'OTHER' })).toThrow('MALFORMED_SHOWCASE_BUNDLE');
		const broken = base();
		(broken.synthetic as { holdout_windows: unknown }).holdout_windows = Number.NaN;
		expect(() => parseShowcase(broken)).toThrow('MALFORMED_SHOWCASE_BUNDLE');
		expect(() => parseShowcase({ ...base(), models: [{ dataset: 'x' }] })).toThrow('MALFORMED_SHOWCASE_BUNDLE');
	});
	it('accepts a bundle without the synthetic section', () => {
		expect(parseShowcase({ ...base(), synthetic: null }).synthetic).toBeNull();
	});
});
