import type { EvalRecord, EvalSummary, StudioRun } from '../types';

export const digest = (n: number): string => n.toString(16).padStart(2, '0').repeat(32);
export const METRICS = { windows: 1446, positives: 307, negatives: 1139, prevalence: 0.21230982019363762, TP: 307, FP: 1139, TN: 0, FN: 0, AUPRC: 0.911570123456789, AUROC: 0.966171, F1: 0.350257, accuracy: 0.2123, precision: 0.2123,
	recall: 1, specificity: 0, balanced_accuracy: 0.5, BCE: 3.499216, Brier: 0.768504, negative_predictive_value: null, undefined: { negative_predictive_value: 'no negative predictions (TN+FN = 0)' }, predicted_positives: 1446, predicted_negatives: 0 };

export function run(over: Partial<StudioRun> = {}): StudioRun {
	return { run_id: 'FL10RUN-AAA', run_length: 10, engine: 'FL10_10R', origin: 'LIVE', run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'PLAIN', source_mode: 'CANONICAL_SYNTHETIC', status: 'RUNNING', phase: 'TRAINING', current_round: 2,
		planned_rounds: 10, client_ids: [], candidate: null, failure: null, label: '10-round extended run', base_model: null, source_label: 'LIVE RUN (this session)', replay_of: null,
		evaluation: { available: true, source: 'LIVE', evaluation_run_id: over.run_id ?? 'FL10RUN-AAA', reason: null, revision: 1 }, export_status: 'NOT_STARTED', created_at: null, ...over };
}

export function record(round: number, status: EvalRecord['evaluation_status'], over: Partial<EvalRecord> = {}, runId = 'FL10RUN-AAA'): EvalRecord {
	const done = status === 'COMPLETED';
	return { run_id: runId, run_length: 10, round_id: round, global_state_digest: digest(round + 1), candidate_id: null, cohort_id: 'WEARABLE_SIM_FL10_EVAL_HOLDOUT_V1', cohort_use: 'REUSED SYNTHETIC DIAGNOSTIC EVALUATION — NOT A NEW UNTOUCHED FINAL TEST',
		evaluation_protocol_id: 'NHM_FL10_SYNTHETIC_EVALUATION_V1', evaluation_status: status, evaluation_queued_at: 't0', evaluation_started_at: status === 'QUEUED' ? null : 't1', evaluation_completed_at: done ? 't2' : null,
		failure: status === 'FAILED' ? { code: 'X', message: 'boom' } : null, threshold: 0.5, calibration: 'NONE', windows: done ? 1446 : null, metric_result: done ? { ...METRICS } : null,
		confusion_counts: done ? { TP: 307, FP: 1139, TN: 0, FN: 0, predicted_positives: 1446, predicted_negatives: 0 } : null, ...over };
}

export function summary(records: EvalRecord[], over: Partial<EvalSummary> = {}): EvalSummary {
	return { run_id: records[0]?.run_id ?? 'FL10RUN-AAA', run_length: 10, evaluation: run().evaluation, records, rounds_expected: Array.from({ length: 11 }, (_, i) => i), comparison: { comparator_round: 3, endpoint_round: 10, paired_available: false },
		evaluation_protocol_id: 'NHM_FL10_SYNTHETIC_EVALUATION_V1', observer_id: 'OBS', cohort_use: records[0]?.cohort_use ?? 'x', cohort_use_detail: 'd', claim_boundary: 'SYNTHETIC_ENGINEERING_EVENT_EVALUATION_ONLY_NOT_AAMI_SVF_OR_CLINICAL', threshold: 0.5,
		calibration: 'NONE', source_label: 'LIVE RUN (this session)', run_status: 'RUNNING', revision: 1, ...over };
}
