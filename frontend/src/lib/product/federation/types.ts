// CAPSTONE_FEDERATION_PRODUCT_CLIENT_V1 (types): mirrors the CAP-007 backend vocabulary exactly.
// Technical state names are never renamed internally; human labels live in labels.ts.

export const ALGORITHMS = ['FEDAVG', 'FEDPROX'] as const;
export type Algorithm = (typeof ALGORITHMS)[number];
export const AGGREGATION_MODES = ['PLAIN', 'SECAGG_SHADOW'] as const;
export type AggregationMode = (typeof AGGREGATION_MODES)[number];
export const RUN_TYPES = ['LIVE_RUN', 'REPLAY'] as const;
export type RunType = (typeof RUN_TYPES)[number];
export const RUN_STATES = ['CREATED', 'RUNNING', 'COMPLETED', 'FAILED'] as const;
export type RunState = (typeof RUN_STATES)[number];
export const ROUND_STATES = ['CREATED', 'COLLECTING', 'LOCAL_TRAINING', 'UPDATES_READY', 'AGGREGATING', 'CANDIDATE_CREATED', 'VALIDATING', 'ACCEPTED_TO_SANDBOX', 'REJECTED', 'COMPLETED', 'FAILED'] as const;
export type RoundState = (typeof ROUND_STATES)[number];
export const CLIENT_STATES = ['IDLE', 'DATA_READY', 'TRAINING', 'UPDATE_READY', 'SUBMITTED', 'REJECTED', 'FAILED'] as const;
export type ClientState = (typeof CLIENT_STATES)[number];
export const SECAGG_STATUSES = ['NOT_USED', 'SHADOW_RUNNING', 'SHADOW_VERIFIED', 'SHADOW_FAILED'] as const;
export type SecAggStatus = (typeof SECAGG_STATUSES)[number];
export const VALIDATION_STATUSES = ['PENDING', 'RUNNING', 'PASSED', 'FAILED'] as const;
export type ValidationStatus = (typeof VALIDATION_STATUSES)[number];
export const CANDIDATE_STATES = ['CREATED', 'VALIDATION_PENDING', 'VALIDATING', 'ACCEPTED_TO_SANDBOX', 'REJECTED', 'ARCHIVED'] as const;
export type CandidateState = (typeof CANDIDATE_STATES)[number];
export const SANDBOX_STATUSES = ['NOT_IN_SANDBOX', 'IN_SANDBOX', 'ARCHIVED'] as const;
export type SandboxStatus = (typeof SANDBOX_STATUSES)[number];

export const FROZEN_SCENARIO = 'FL_SINGLE_RUN' as const;
export const FROZEN_ROUNDS = 3 as const;
export const FROZEN_BASE = 'FL_INIT_V2' as const;
export const FROZEN_CLIENTS = 8 as const;
export const GOVERNANCE_CHECK_IDS = ['STATE_FINITE', 'STATE_SPEC_MATCHES_BASE', 'UPDATE_DIGESTS_RECONCILE', 'ROUND_ACCEPTED_UPDATE_COUNT_COMPLETE', 'BASE_STATE_LINEAGE_VERIFIED'] as const;

export interface FederationRun {
	run_id: string;
	run_type: RunType;
	base_model_id: string;
	federation_protocol_id: string;
	algorithm: Algorithm;
	client_ids: string[];
	planned_rounds: number;
	current_round: number;
	started_at_us: number | null;
	completed_at_us: number | null;
	status: RunState;
	secagg_mode: AggregationMode;
	candidate_ids: string[];
	engineering_only: true;
}

export interface FederationRound {
	run_id: string;
	round_id: number;
	state: RoundState;
	participating_client_ids: string[];
	base_state_digest: string;
	algorithm: Algorithm;
	accepted_update_count: number;
	candidate_id: string | null;
}

export interface FLClientIdentity {
	client_id: string;
	edge_node_id: string;
	base_model_id: string;
	global_round: number;
	local_example_count: number;
	client_state: ClientState;
	update_digest: string | null;
	eligible: boolean;
	ineligible_reason: string | null;
}

export interface FederationOverview {
	federation_runtime: 'ENABLED_ENGINEERING';
	engineering_only: true;
	scientific_evidence: false;
	production_deployed: false;
	banner: string;
	client_count: number;
	cohort_id: string;
	active_live_run: boolean;
	candidate_count: number;
	released_model_id: string;
	secagg_claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY';
}

export interface ReleasedModelRef {
	model_id: string;
	namespace: 'RELEASED_SCIENTIFIC';
	role: 'RELEASED_DEFAULT' | 'ROLLBACK_REFERENCE';
}

export interface CandidateModel {
	candidate_id: string;
	parent_model_id: string;
	federation_run_id: string;
	round: number;
	algorithm: Algorithm;
	client_count: number;
	created_at_us: number;
	state_digest: string;
	validation_status: ValidationStatus;
	governance_status: CandidateState;
	sandbox_status: SandboxStatus;
	production_deployed: false;
	claim_boundary: string;
}

export interface ModelRegistryView {
	registry_id: string;
	released_default_model_id: string;
	released_scientific: ReleasedModelRef[];
	capstone_fl_candidates: CandidateModel[];
}

/** The ONLY request body the product may send: no model/hyperparameter field exists. */
export interface CreateFederationRunRequest {
	run_type: RunType;
	algorithm: Algorithm;
	secagg_mode: AggregationMode;
	planned_rounds: number;
	scenario_id: string;
}

export const FEDERATION_EVENT_KINDS = [
	'federation.status', 'round.status', 'client.status', 'client.training_progress', 'client.update_ready',
	'aggregation.status', 'secagg.status', 'candidate.created', 'candidate.validation', 'candidate.governance',
	'federation.completed', 'federation.error'
] as const;
export type FederationEventKind = (typeof FEDERATION_EVENT_KINDS)[number];

interface Envelope {
	contract_version: 'PRODUCT_LIVE_EVENT_V1';
	event_id: string;
	sequence_index: number;
	emitted_at_us: number;
	run_id: string;
}
export type FederationEvent = Envelope &
	(
		| { event_type: 'federation.status'; payload: { run_type: RunType; run_status: RunState; algorithm: Algorithm; current_round: number; planned_rounds: number; client_count: number; engineering_only: true } }
		| { event_type: 'round.status'; payload: { round_id: number; round_state: RoundState; accepted_updates: number; expected_updates: number } }
		| { event_type: 'client.status'; payload: { client_id: string; client_state: ClientState; local_example_count: number; reason_code: string | null } }
		| { event_type: 'client.training_progress'; payload: { client_id: string; round_id: number; progress_fraction: number; examples_seen: number } }
		| { event_type: 'client.update_ready'; payload: { client_id: string; round_id: number; update_digest: string; examples_seen: number } }
		| { event_type: 'aggregation.status'; payload: { round_id: number; algorithm: Algorithm; aggregation_mode: AggregationMode; accepted_updates: number; state_digest: string | null } }
		| { event_type: 'secagg.status'; payload: { round_id: number; mode: AggregationMode; status: SecAggStatus; claim_scope: 'PROTECTED_AGGREGATION_INTERFACE_ONLY' } }
		| { event_type: 'candidate.created'; payload: { candidate_id: string; parent_model_id: string; round_id: number; state_digest: string; production_deployed: false } }
		| { event_type: 'candidate.validation'; payload: { candidate_id: string; validation_status: ValidationStatus; checks: string[] } }
		| { event_type: 'candidate.governance'; payload: { candidate_id: string; governance_status: CandidateState; sandbox_status: SandboxStatus; production_deployed: false } }
		| { event_type: 'federation.completed'; payload: { rounds_completed: number; candidate_ids: string[]; production_deployed: false } }
		| { event_type: 'federation.error'; payload: { error_code: string; message: string; recoverable: boolean; round_id: number | null } }
	);
