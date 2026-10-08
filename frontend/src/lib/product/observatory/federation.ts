import { parseWindowTrace, type WindowTrace } from './types';

type RecordLike = Record<string, unknown>;
function object(value: unknown): RecordLike {
	if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	return value as RecordLike;
}
function string(value: unknown): string {
	if (typeof value !== 'string') throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	return value;
}
function number(value: unknown): number {
	if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	return value;
}
function array(value: unknown): unknown[] {
	if (!Array.isArray(value)) throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	return value;
}
const nullable = <T>(value: unknown, parse: (v: unknown) => T): T | null => value === null ? null : parse(value);

export interface FrozenClient {
	client_id: string; participant_id: string; session_id: string; source_rate_hz: number;
	scenario: string; windows_emitted: number; valid: number; degraded: number; unusable: number;
	trainable: number; synthetic_positive: number; synthetic_negative: number; dataset_sha256: string;
	faults: [string, number, number][];
}
export interface FrozenCohort {
	cohort_id: string; source_relative_path: string; source_sha256: string; label_contract: string;
	claim_boundary: string; clients: FrozenClient[];
}
export interface ClientContribution {
	client_id: string; local_trainable_windows: number; examples_seen: number | null;
	shuffle_seed: string | null; update_digest: string | null;
	training_completed: boolean | null; update_produced: boolean | null;
	update_submitted: boolean | null; accepted: boolean | null; aggregated: boolean | null;
	accepted_examples: number | null; weight: number | null; evidence_state: string;
	training_readout: LocalTrainingDiagnostic | null;
}
export interface LocalTrainingDiagnostic {
	examples_seen: number; batch_count: number; shuffle_seed: string; update_bytes: number;
	mean_local_loss: number; update_norm: number;
	per_batch: { batches: BatchRow[]; dropped_beyond_bound: number; loss_term: string } | null;
}
export interface BatchRow { batch_index: number; batch_size: number; loss: number; learning_rate: number; gradient_l2_norm: number; optimizer_step: number }
export interface RoundContribution {
	round_id: number; base_state_digest: string | null; committed_state_digest: string | null;
	accepted_update_count: number | null; reported_accepted_update_count: number | null;
	accepted_example_total: number | null; acceptance_basis: string; clients: ClientContribution[];
}
export interface RunContributions {
	run_id: string; run_type: string; run_status: string; algorithm: string; source_run_id: string | null;
	evidence_status: string; cohort_manifest_sha256: string; reported_total_accepted_updates: number | null;
	claim_boundary: string;
	rounds: RoundContribution[];
}
export interface FlClientWindowTrace {
	client_id: string; participant_id: string; cohort_manifest_sha256: string;
	label_contract: string; training_eligible: boolean; engineering_label: number | null;
	claim_boundary: string; signal: WindowTrace;
}
export function parseFlClientWindowTrace(value: unknown): FlClientWindowTrace {
	const x = object(value);
	if (typeof x.training_eligible !== 'boolean') throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	const label = nullable(x.engineering_label, number);
	if (label !== null && label !== 0 && label !== 1) throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	if (!x.training_eligible && label !== null) throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
	return { client_id: string(x.client_id), participant_id: string(x.participant_id),
		cohort_manifest_sha256: string(x.cohort_manifest_sha256), label_contract: string(x.label_contract),
		training_eligible: x.training_eligible, engineering_label: label,
		claim_boundary: string(x.claim_boundary), signal: parseWindowTrace(x.signal) };
}
export function parseFrozenCohort(value: unknown): FrozenCohort {
	const x = object(value);
	return { cohort_id: string(x.cohort_id), source_relative_path: string(x.source_relative_path),
		source_sha256: string(x.source_sha256), label_contract: string(x.label_contract),
		claim_boundary: string(x.claim_boundary), clients: array(x.clients).map((raw) => {
			const c = object(raw);
			return { client_id: string(c.client_id), participant_id: string(c.participant_id),
				session_id: string(c.session_id), source_rate_hz: number(c.source_rate_hz),
				scenario: string(c.scenario), windows_emitted: number(c.windows_emitted),
				valid: number(c.valid), degraded: number(c.degraded), unusable: number(c.unusable),
				trainable: number(c.trainable), synthetic_positive: number(c.synthetic_positive),
				synthetic_negative: number(c.synthetic_negative), dataset_sha256: string(c.dataset_sha256),
				faults: array(c.faults).map((v) => {
					const f = array(v); if (f.length !== 3) throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
					return [string(f[0]), number(f[1]), number(f[2])];
				})
			};
		}) };
}
export function parseRunContributions(value: unknown): RunContributions {
	const x = object(value);
	return { run_id: string(x.run_id), run_type: string(x.run_type), run_status: string(x.run_status),
		algorithm: string(x.algorithm), source_run_id: nullable(x.source_run_id, string),
		evidence_status: string(x.evidence_status), cohort_manifest_sha256: string(x.cohort_manifest_sha256),
		reported_total_accepted_updates: nullable(x.reported_total_accepted_updates, number),
		claim_boundary: string(x.claim_boundary), rounds: array(x.rounds).map((raw) => {
			const r = object(raw);
			return { round_id: number(r.round_id), base_state_digest: nullable(r.base_state_digest, string),
				committed_state_digest: nullable(r.committed_state_digest, string),
				accepted_update_count: nullable(r.accepted_update_count, number),
				reported_accepted_update_count: nullable(r.reported_accepted_update_count, number),
				accepted_example_total: nullable(r.accepted_example_total, number),
				acceptance_basis: string(r.acceptance_basis),
				clients: array(r.clients).map((item) => {
					const c = object(item);
					for (const flag of [c.training_completed, c.update_produced, c.update_submitted, c.accepted, c.aggregated]) {
						if (flag !== null && typeof flag !== 'boolean') throw new Error('MALFORMED_OBSERVATORY_FEDERATION');
					}
					return { client_id: string(c.client_id), local_trainable_windows: number(c.local_trainable_windows),
						examples_seen: nullable(c.examples_seen, number), shuffle_seed: nullable(c.shuffle_seed, string),
						update_digest: nullable(c.update_digest, string),
						training_completed: c.training_completed as boolean | null,
						update_produced: c.update_produced as boolean | null,
						update_submitted: c.update_submitted as boolean | null,
						accepted: c.accepted as boolean | null, aggregated: c.aggregated as boolean | null,
						accepted_examples: nullable(c.accepted_examples, number), weight: nullable(c.weight, number),
						training_readout: c.training_diagnostic == null ? null : (() => {
							const d = object(c.training_diagnostic);
							return { examples_seen: number(d.examples_seen), batch_count: number(d.batch_count),
								shuffle_seed: string(d.shuffle_seed), update_bytes: number(d.update_bytes),
								mean_local_loss: number(d.mean_loss_diagnostic_only),
								update_norm: number(d.update_norm_diagnostic_only),
								per_batch: d.per_batch == null ? null : (() => {
									const pb = object(d.per_batch);
									return { loss_term: string(pb.loss_term), dropped_beyond_bound: number(pb.dropped_beyond_bound),
										batches: array(pb.batches).map((raw) => { const b = object(raw);
											return { batch_index: number(b.batch_index), batch_size: number(b.batch_size), loss: number(b.loss), learning_rate: number(b.learning_rate),
												gradient_l2_norm: number(b.gradient_l2_norm), optimizer_step: number(b.optimizer_step) }; }) };
								})() };
						})(),
						evidence_state: string(c.evidence_state) };
				}) };
		}) };
}
