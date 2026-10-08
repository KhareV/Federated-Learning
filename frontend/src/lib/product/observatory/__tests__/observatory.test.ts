import { describe, expect, it } from 'vitest';
import { parseFlClientWindowTrace, parseFrozenCohort, parseRunContributions } from '../federation';
import { parseResearchRecords } from '../research';

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
					accepted_examples: null, weight: null, evidence_state: 'TRAINED_ACCEPTANCE_NOT_RECORDED' }] }]
		});
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
});
