import { describe, expect, it } from 'vitest';
import { parseActivationInspection } from '../evidence';
import { parseRunContributions } from '../federation';

const baseInspection = {
	classification: 'ON_DEMAND_FORWARD_HOOK_OBSERVATION_RELEASED_CHECKPOINT_ON_SYNTHETIC_WINDOW', scenario_id: 'NORMAL_MONITORING', window_index: 2, window_quality: 'VALID', model_id: 'MODEL_V2_FINAL', parameter_count: 57553,
	raw_logit: -5.5, raw_probability: 0.004, parity: { logit_bit_identical_with_and_without_hooks: true, hooks_remaining_after_inspection: 0 },
	layers: [{ name: 'backbone.stem_conv', type: 'Conv1d', output_shape: [1, 24, 1250], mean: 0, std: 1, min: -1, max: 1, l2_norm: 3, fraction_exactly_zero: 0 }], selected_layer: 'backbone.stem_conv',
	selected_layer_heatmap: { channels: 1, time_bins: 2, source_time_steps: 4, mean_pooled_values: [[0.1, 0.2]] }, caveats: ['not clinical']
};

describe('OBS-DIAG-001 evidence parsing', () => {
	it('shows an activation inspection only when hook parity is verified and no hooks remain', () => {
		expect(parseActivationInspection(baseInspection).heatmap?.channels).toBe(1);
		expect(() => parseActivationInspection({ ...baseInspection, parity: { logit_bit_identical_with_and_without_hooks: false, hooks_remaining_after_inspection: 0 } })).toThrow('MALFORMED_OBSERVATORY_EVIDENCE');
		expect(() => parseActivationInspection({ ...baseInspection, parity: { logit_bit_identical_with_and_without_hooks: true, hooks_remaining_after_inspection: 1 } })).toThrow('MALFORMED_OBSERVATORY_EVIDENCE');
		expect(() => parseActivationInspection({ ...baseInspection, classification: 'INVENTED' })).toThrow('MALFORMED_OBSERVATORY_EVIDENCE');
	});
	it('parses exact per-batch rows and keeps absent capture as null', () => {
		const client = (extra: object) => ({ client_id: 'SIM_FL_SITE_00', local_trainable_windows: 93, examples_seen: 93, shuffle_seed: '1', update_digest: 'd', training_completed: true, update_produced: true, update_submitted: true, accepted: true, aggregated: true, accepted_examples: 93, weight: 1, evidence_state: 'DIRECT_OBSERVED_ACCEPTED', ...extra });
		const diag = { examples_seen: 93, batch_count: 2, shuffle_seed: '1', update_bytes: 10, mean_loss_diagnostic_only: 0.5, update_norm_diagnostic_only: 1 };
		const view = parseRunContributions({ run_id: 'r', run_type: 'LIVE_RUN', run_status: 'COMPLETED', algorithm: 'FEDAVG', source_run_id: null, evidence_status: 'x', cohort_manifest_sha256: 's', reported_total_accepted_updates: 24, claim_boundary: 'c',
			rounds: [{ round_id: 1, base_state_digest: 'b', committed_state_digest: 'c', accepted_update_count: 1, reported_accepted_update_count: 1, accepted_example_total: 93, acceptance_basis: 'DIRECT_OBSERVED_COORDINATOR_MAP',
				clients: [client({ training_diagnostic: { ...diag, per_batch: { loss_term: 'BCE_WITH_LOGITS_MEAN_OVER_BATCH', dropped_beyond_bound: 0, batches: [{ batch_index: 0, batch_size: 64, loss: 0.7, learning_rate: 0.001, gradient_l2_norm: 1.2, optimizer_step: 1 }, { batch_index: 1, batch_size: 29, loss: 0.1, learning_rate: 0.001, gradient_l2_norm: 0.4, optimizer_step: 2 }] } } }), client({ client_id: 'SIM_FL_SITE_01', training_diagnostic: diag })] }] });
		expect(view.rounds[0].clients[0].training_readout?.per_batch?.batches[1].batch_size).toBe(29);
		expect(view.rounds[0].clients[1].training_readout?.per_batch).toBeNull();
	});
});
