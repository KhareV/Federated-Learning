import { describe, expect, it } from 'vitest';
import { parseFlClientWindowTrace, parseFrozenCohort, parseRunContributions } from '../federation';
import { parseResearchRecords } from '../research';
import { parseCalibration, parseFlCurves, parseFlEval } from '../evidence';

describe('Observatory evidence validation', () => {
	it('rejects malformed cohort and run metadata instead of treating it as evidence', () => {
		expect(() => parseFrozenCohort({ cohort_id: 'fake', clients: [] })).toThrow('MALFORMED_OBSERVATORY_FEDERATION');
		expect(() => parseRunContributions({ run_id: 'fake', rounds: [{ clients: [] }] })).toThrow('MALFORMED_OBSERVATORY_FEDERATION');
	});
	it('keeps absent acceptance distinct from rejection and preserves large seeds as strings', () => {
		const view = parseRunContributions({
			run_id: 'run', run_type: 'LIVE_RUN', run_status: 'COMPLETED', algorithm: 'FEDAVG',
			source_run_id: null, evidence_status: 'RUN_ARTIFACT_METADATA', cohort_manifest_sha256: 'sha',
			reported_total_accepted_updates: 8, claim_boundary: 'ENGINEERING_SAMPLE_WEIGHT_NOT_ACCURACY_OR_EFFICACY',
			rounds: [{ round_id: 3, base_state_digest: 'base', committed_state_digest: 'final',
				accepted_update_count: null, reported_accepted_update_count: 8, accepted_example_total: null,
				acceptance_basis: 'NOT_RECORDED',
				clients: [{ client_id: 'SIM_FL_SITE_00', local_trainable_windows: 93, examples_seen: 93,
					shuffle_seed: '11295175845878697379', update_digest: 'digest',
					training_completed: true, update_produced: true, update_submitted: null,
					accepted: null, aggregated: null,
					accepted_examples: null, weight: null, evidence_state: 'TRAINED_ACCEPTANCE_NOT_RECORDED',
					training_diagnostic: { examples_seen: 93, batch_count: 2, shuffle_seed: '1', update_bytes: 10,
						mean_loss_diagnostic_only: 0.5, update_norm_diagnostic_only: 1.5 } },
					{ client_id: 'SIM_FL_SITE_01', local_trainable_windows: 91, examples_seen: null, shuffle_seed: null,
						update_digest: null, training_completed: null, update_produced: null, update_submitted: null,
						accepted: null, aggregated: null, accepted_examples: null, weight: null, evidence_state: 'NOT_RECORDED' }] }]
		});
		expect(view.rounds[0].clients[0].training_readout?.batch_count).toBe(2);
		expect(view.rounds[0].clients[0].training_readout?.mean_local_loss).toBe(0.5);
		expect(view.rounds[0].clients[1].training_readout).toBeNull();
		expect(view.rounds[0].reported_accepted_update_count).toBe(8);
		expect(view.rounds[0].clients[0].accepted).toBeNull();
		expect(view.rounds[0].clients[0].weight).toBeNull();
		expect(view.rounds[0].clients[0].shuffle_seed).toBe('11295175845878697379');
	});
	it('rejects a training label on an excluded synthetic window', () => {
		const excluded = {
			client_id: 'SIM_FL_SITE_07', participant_id: 'SIM_P000108', cohort_manifest_sha256: 'sha',
			label_contract: 'WEARABLE_SIM_EVENT_WINDOW_V1', training_eligible: false,
			engineering_label: 1, claim_boundary: 'SYNTHETIC_ENGINEERING_LABEL_NOT_AAMI_SVF', signal: {}
		};
		expect(() => parseFlClientWindowTrace(excluded)).toThrow('MALFORMED_OBSERVATORY_FEDERATION');
	});
	it('fails closed if a research-record listing contains a held-out partition', () => {
		const item = { dataset_id: 'MITDB', record_id: '101', participant_group_id: 'MITDB_P101',
			partition: 'TRAIN', eligible_window_count: 356,
			source_kind: 'FROZEN_PROCESSED_RESEARCH_CACHE' };
		expect(parseResearchRecords([item])).toHaveLength(1);
		expect(() => parseResearchRecords([{ ...item, partition: 'INTERNAL_TEST' }])).toThrow();
	});
	it('parses frozen calibration with empty reliability bins and refuses unlabeled calibration', () => {
		const bin = (count: number) => ({ lower: 0, upper: 0.1, count, mean_probability: count ? 0.05 : null, observed_positive_fraction: count ? 0.1 : null });
		const base = { label: 'MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY', constants: { temperature: 52.88, threshold: 0.51 }, probability_semantics: { raw_probability: 'r', source_domain_calibrated_probability: 'c' },
			reliability: { method: 'EQUAL_WIDTH_10_BINS_V1', raw: [bin(0), bin(4)], temperature_scaled: [bin(2)] }, not_applicable_to: 'candidate', source: { calibration_sha256: 'a', reliability_sha256: 'b' } };
		const parsed = parseCalibration(base);
		expect(parsed.raw[0].observed_positive_fraction).toBe(0);
		expect(parsed.raw[1].count).toBe(4);
		expect(() => parseCalibration({ ...base, label: 'CALIBRATED FOR EVERYONE' })).toThrow('MALFORMED_OBSERVATORY_EVIDENCE');
	});
	it('only accepts evidence that declares its classification', () => {
		expect(() => parseFlEval({ classification: 'SOMETHING_ELSE', datasets: {}, limitations: [] })).toThrow('MALFORMED_OBSERVATORY_EVIDENCE');
		expect(parseFlEval({ classification: 'FROZEN_RESEARCH_EVIDENCE', datasets: {}, limitations: ['x'] }).limitations).toEqual(['x']);
		expect(() => parseFlCurves({ classification: 'INVENTED_CURVE' })).toThrow('MALFORMED_OBSERVATORY_EVIDENCE');
	});
});
