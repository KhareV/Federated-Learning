// NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 -- typed, fail-closed models of the Studio REST payloads. Values are validated and passed through; nothing is computed here.
export const RUN_LENGTHS = [3, 10] as const;
export type RunLength = (typeof RUN_LENGTHS)[number];
export type EvaluationStatus = 'QUEUED' | 'EVALUATING' | 'COMPLETED' | 'FAILED';
export type RoundEvalStatus = EvaluationStatus | 'NOT_SUBMITTED';
export type RunOrigin = 'LIVE' | 'REPLAY' | 'RECORDED';
export type SourceMode = 'CANONICAL_SYNTHETIC' | 'LIVE_MONITORED_SITE_00';
export type Initialisation = 'FL_INIT_V2' | 'MODEL_V2_FINAL';
export interface BaseModel { model_id: Initialisation; label: string; state_sha256?: string | null; checkpoint_sha256?: string | null; state_entries?: number | null; architecture_id?: string | null; training_target_of_checkpoint?: string | null }
export type ExportStatus = 'NOT_STARTED' | 'PREPARING' | 'READY' | 'FAILED';

export interface StudioCapabilities {
	studio_id: string;
	run_lengths: number[];
	default_run_length: number;
	ten_round: { available: boolean; initialisations?: { id: Initialisation; label: string; default: boolean }[]; source_modes: SourceMode[]; algorithms: string[]; aggregation_modes: string[]; unsupported: Record<string, string>; expected_updates: number };
	three_round: { available: boolean; expected_updates: number };
	generalisation?: { cohort_id: string; label: string; claim_boundary: string; baseline: string };
	evaluation: { observer_id: string; protocol_id: string; threshold: number; calibration: string; cohort_use: string; cohort_use_detail: string; claim_boundary: string };
}

export interface EvaluationAvailability { available: boolean; source: 'LIVE' | 'RECORDED' | 'RECORDED_FROM_SOURCE_RUN'; evaluation_run_id: string; reason: string | null; revision: number }

export interface StudioRun {
	run_id: string;
	run_length: RunLength;
	engine: 'PRODUCT_3R' | 'FL10_10R';
	origin: RunOrigin;
	run_type: 'LIVE_RUN' | 'REPLAY';
	algorithm: string;
	secagg_mode: string;
	source_mode: SourceMode;
	status: 'CREATED' | 'RUNNING' | 'COMPLETED' | 'FAILED';
	phase: string;
	current_round: number;
	planned_rounds: number;
	client_ids: string[];
	candidate: { candidate_id: string | null; state_sha256?: string | null; promoted: boolean; deployed: boolean; label?: string } | null;
	failure: { code: string; message: string } | null;
	label: string;
	base_model: BaseModel | null;
	source_label: string;
	replay_of: string | null;
	evaluation: EvaluationAvailability;
	export_status: ExportStatus;
	created_at: string | null;
}

export type Metrics = Record<string, number | string | null | Record<string, unknown> | number[]>;
export interface EvalRecord {
	run_id: string;
	run_length: number;
	round_id: number;
	global_state_digest: string;
	candidate_id: string | null;
	cohort_id: string;
	cohort_use: string;
	evaluation_protocol_id: string;
	evaluation_status: EvaluationStatus;
	evaluation_queued_at: string | null;
	evaluation_started_at: string | null;
	evaluation_completed_at: string | null;
	failure: { code: string; message: string } | null;
	threshold: number;
	calibration: string;
	windows: number | null;
	metric_result: Metrics | null;
	confusion_counts: Record<string, number> | null;
	prediction_artifact_reference?: { path: string; sha256: string } | null;
	curve_artifact_reference?: { path: string; sha256: string } | null;
	source_digest?: string | null;
	claim_boundary?: string;
	source?: 'RECORDED';
}

export interface EvalSummary {
	run_id: string;
	run_length: RunLength;
	evaluation: EvaluationAvailability;
	records: EvalRecord[];
	rounds_expected: number[];
	comparison: { comparator_round: number; endpoint_round: number; paired_available: boolean };
	evaluation_protocol_id: string;
	observer_id: string;
	cohort_use: string;
	cohort_use_detail: string;
	claim_boundary: string;
	threshold: number;
	calibration: string;
	source_label: string;
	run_status: string;
	revision: number;
}

export interface EvalRoundDetail extends Omit<Partial<EvalRecord>, 'evaluation_status'> {
	run_id: string;
	round_id: number;
	evaluation_status: RoundEvalStatus;
	reason?: string;
	participant_metrics?: Record<string, Metrics>;
	participant_summary?: { participant_macro_F1: number | null; participants_defined: number; participants_undefined: number };
	curves?: { roc: number[][]; pr: number[][] } | null;
}

export interface StudioSpecView { id: string; label: string; kind: string; pending?: { x: number; state: string; status: string }[]; [key: string]: unknown }
export interface StudioSpec { id: string; title: string; caption: string; sources: string[]; group: string; synthetic_label: string; note: string | null; availability: 'AVAILABLE' | 'PARTIAL' | 'PENDING'; availability_detail: string; views: StudioSpecView[] }
export interface StudioFigures { run_id: string; revision: number | null; selected_round: number | null; source_label: string; specs: Record<string, StudioSpec> }
export interface StudioTable { id: string; title: string; columns: string[]; rows: unknown[][]; caption: string; sources: string[]; synthetic_label: string; availability: 'AVAILABLE' | 'PENDING' }
export interface StudioTables { run_id: string; revision: number | null; source_label: string; tables: Record<string, StudioTable> }

export interface ExportEntry { path: string; sha256: string; rows?: number }
export interface StudioExports {
	status: ExportStatus;
	message?: string;
	run_id: string;
	figures?: Record<string, Record<string, ExportEntry>>;
	tables?: Record<string, Record<string, ExportEntry>>;
	data?: Record<string, Record<string, ExportEntry>>;
	source_label?: string;
	cohort_use?: string;
}

export interface RoundDetail {
	run_id: string;
	round_id: number;
	committed: boolean;
	round: Record<string, unknown> | null;
	client_rounds: Record<string, unknown>[];
	batches: Record<string, unknown>[];
	state: Record<string, unknown> | null;
}

export interface BridgeRow { dataset: string; [key: string]: unknown }
export interface StudioOverview {
	run_id: string; run_length: RunLength; engine: string; origin: RunOrigin; source_label: string; mode: string; source_mode: SourceMode; synthetic_label: string; live_label: string | null; status: string;
	run: Record<string, unknown>;
	protocol: { id?: string; evaluation_protocol_id?: string; sha256?: string; holdout_manifest_sha256?: string; interpretation_boundaries?: string[]; research_question?: string; primary_comparison?: unknown };
	evaluation: { windows: number; threshold: number; calibration: string; round_selection: string; method_freeze_commit: string; separation: Record<string, unknown>; separation_source: string; cohort_use: string; cohort_use_detail: string; comparator: string; endpoint: string; holdout_participants: { holdout_id: string; participant_id: string; site_condition: string }[] };
	rounds: { round: number; accepted_updates: number; rejected_updates: number; weighted_mean_training_loss: number | null; round_duration_seconds: number | null; global_state_sha256: string; base_state_sha256: string; candidate_status: string; aggregated_update_norm: number | null }[];
	state_progression: Record<string, string>;
	monitoring_link: { label: string; site00_source: string; monitoring_sessions_executed: number; buffer_reused_for_rounds: number } | null;
	scientific_bridge: { comparability_rows: BridgeRow[]; verdict: string; limitations: string[]; route: string; note: string };
	historical_exposed: string;
}

export interface StudioRunChoice { run_length: RunLength; source_mode: SourceMode; initialisation?: Initialisation }

// ---- Generalisation lane (frozen V2 vs every federated round on the unseen G1 cohort) --------------------------------------------
export interface GenRecord extends EvalRecord { subject: 'FL_ROUND' | 'FROZEN_V2_BASELINE' }
export interface GenInterval { lower: number | null; upper: number | null; valid_replicates: number }
export interface GenPairMetric { A_point: number | null; B_point: number | null; difference_point: number | null; difference_interval: GenInterval; invalid_replicates: number }
export interface GenPair { clusters: number; replicates: number; seed: number; method: string; multiplicity: string; metrics: Record<string, GenPairMetric>; identical_predictions: boolean }
export interface GenRound { round_id: number; record: GenRecord | null; paired_vs_v2: GenPair | null }
export interface GenCohort {
	cohort_id: string; label: string; detail: string; participants: number; windows: number; positive_windows: number; participant_ids: string[]; site_conditions: string[];
	manifest_sha256: string | null; separation: Record<string, Record<string, number>> | null; separation_note: string | null;
}
export interface Generalisation {
	schema_version: 'STUDIO_GENERALISATION_V1';
	run_id: string; run_length: number; observer_id: string; claim_boundary: string; threshold: number; calibration: string;
	base_model: BaseModel;
	cohort: GenCohort;
	baseline: { label: string; detail: string; record: GenRecord | null; state_sha256: string | null };
	rounds: GenRound[];
	integrity: { r0_digest_equals_frozen_v2: boolean | null; r0_predictions_equal_frozen_v2: boolean | null };
	metrics_order: string[]; lower_is_better: string[]; interpretation: string[]; revision: number;
}
export interface GenCurves { run_id: string; round_id: number; available: boolean; reason?: string; round?: { roc: number[][]; pr: number[][] }; baseline?: { roc: number[][]; pr: number[][] } | null }
export interface GenParticipants { run_id: string; round_id: number; available: boolean; round?: Record<string, Metrics>; baseline?: Record<string, Metrics> | null }
