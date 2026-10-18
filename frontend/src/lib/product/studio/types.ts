// NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 -- typed, fail-closed models of the Studio REST payloads. Values are validated and passed through; nothing is computed here.
export const RUN_LENGTHS = [3, 10] as const;
export type RunLength = (typeof RUN_LENGTHS)[number];
export type EvaluationStatus = 'QUEUED' | 'EVALUATING' | 'COMPLETED' | 'FAILED';
export type RoundEvalStatus = EvaluationStatus | 'NOT_SUBMITTED';
export type RunOrigin = 'LIVE' | 'REPLAY' | 'RECORDED';
export type SourceMode = 'CANONICAL_SYNTHETIC' | 'LIVE_MONITORED_SITE_00';
export type Initialisation = 'FL_INIT_V2' | 'MODEL_V2_FINAL' | 'CANDIDATE';
export type BaseModelId = 'FL_INIT_V2' | 'MODEL_V2_FINAL' | 'HARDWARE_DEMO_MODEL_V1';
export type RunSourceMode = SourceMode | 'RECORDED_HARDWARE';
export interface BaseModel { /** A known base model, or (kind CANDIDATE) the id of the stored engineering candidate the run started from. */ model_id: BaseModelId | string; kind?: 'CANDIDATE' | null; candidate_cohort?: CohortId | null; source_run_id?: string | null; parent_model_id?: string | null; initialisation?: 'FRESH_SEEDED' | 'WARM_START' | null; label: string; state_sha256?: string | null; checkpoint_sha256?: string | null; state_entries?: number | null; architecture_id?: string | null; training_target_of_checkpoint?: string | null }
export type ExportStatus = 'NOT_STARTED' | 'PREPARING' | 'READY' | 'FAILED';

export type CohortId = 'ORIGINAL' | 'REALISTIC';
export interface CohortOption { id: CohortId; label: string; description: string; client_ids: string[]; evaluation_cohort_id: string; cohort_use: string; claim_boundary: string; default: boolean }

export interface StudioCandidate {
	schema_version: string; candidate_id: string; label: string; created_at: string; source_run_id: string; source_kind: 'SYNTHETIC_COHORT' | 'LIVE_MONITORED_SITE' | 'RECORDED_HARDWARE'; source_detail: Record<string, unknown>;
	cohort: CohortId; cohort_label: string; evaluation_cohort_id: string | null; run_length: number; round_id: number; algorithm: string; secagg_mode: string; base_model: Record<string, unknown>; state_sha256: string;
	metrics: Record<string, number> | null; promoted: false; deployed: false; registered_in_product_registry: false; used_for_monitoring: false;
}

export interface StudioCapabilities {
	studio_id: string;
	run_lengths: number[];
	default_run_length: number;
	ten_round: { available: boolean; initialisations?: { id: Initialisation; label: string; default: boolean }[]; rounds_by_initialisation?: Partial<Record<Initialisation, number[]>>; default_initialisation?: Initialisation; source_modes: SourceMode[]; algorithms: string[]; aggregation_modes: string[]; unsupported: Record<string, string>; expected_updates: number; monitored_sites?: { index: number; client_id: string; label: string; profile: string }[]; cohorts?: CohortOption[]; cohort_note?: string };
	candidate_library?: { available: boolean; count: number; rounds?: number[]; note: string };
	three_round: { available: boolean; expected_updates: number };
	hardware_demo?: { available: boolean; source_mode: 'RECORDED_HARDWARE_DEMO'; model: 'HARDWARE_DEMO_MODEL_V1'; run_lengths: number[]; algorithms: string[]; aggregation_modes: string[]; secagg_scope: string; fedprox_mu: number; label_assignment: string; initialisations: string[]; v2_initialisation: string; starting_models?: HardwareStartingModel[] };
	generalisation?: { cohort_id: string; label: string; claim_boundary: string; baseline: string };
	evaluation: { observer_id: string; protocol_id: string; threshold: number; calibration: string; cohort_use: string; cohort_use_detail: string; claim_boundary: string };
}

export interface HardwareDemoSession { id: string; started_at: string; stopped_at: string; record_count: number; trace_count: number; eligible: boolean }
export interface HardwareDemoRound { round: number; base_state_sha256: string; global_state_sha256: string; accepted_updates: number; rejected_updates: number; weighted_mean_training_loss: number; optimizer_steps: number; evaluation: { BCE: number; accuracy: number; precision: number | null; recall: number | null; F1: number | null; windows: number; confusion: Record<string, number> } }
export interface HardwareDemoRun { schema_version: 'HARDWARE_DEMO_FL_RUN_V1'; run_id: string; created_at: string; completed_at: string; status: 'COMPLETED'; source_mode: 'RECORDED_HARDWARE_DEMO'; source_session_ids: string[]; source_record_count: number; snapshot_sha256: string; algorithm: 'FEDAVG' | 'FEDPROX'; fedprox_mu: number | null; aggregation: 'PLAIN'; secagg_mode: 'PLAIN' | 'SECAGG_SHADOW'; secagg_shadow: Record<string, unknown> | null; rounds_planned: 3 | 10; rounds: HardwareDemoRound[]; state_progression: Record<string, string>; model: { id: 'HARDWARE_DEMO_MODEL_V1' | 'MODEL_V2_FINAL'; architecture: string; released: false; v2_initialisation: 'NOT_APPLICABLE' | 'PRETRAINED_V2_FINE_TUNING'; initialisation?: 'FRESH_SEEDED' | 'WARM_START' | 'MODEL_V2_FINAL'; warm_start?: { source_run_id: string; source_round: number; source_state_sha256: string; source_algorithm: string | null } | null }; dataset: { training_windows: number; holdout_windows: number; windows_total: number; input_feature_sha256: string; label_sha256: string; label_assignment: { version: string; status: 'SYNTHETIC_ASSIGNED_FOR_DEMO'; seed: number; classes: Record<string, string> }; clients: Record<string, { samples: number; label_counts: Record<string, number>; feature_sha256: string; window_ids: string[] }> }; claim_boundary: string }
export interface HardwareDemoChoice { session_ids: string[]; run_length: 3 | 10; algorithm: 'FEDAVG' | 'FEDPROX'; secagg_mode: 'PLAIN' | 'SECAGG_SHADOW'; label_seed: number; initialisation?: 'FRESH_SEEDED' | 'WARM_START' | 'MODEL_V2_FINAL' | 'CANDIDATE'; warm_start_run_id?: string; cohort?: CohortId; candidate_id?: string }

export interface EvaluationAvailability { available: boolean; source: 'LIVE' | 'RECORDED' | 'RECORDED_FROM_SOURCE_RUN'; evaluation_run_id: string; reason: string | null; revision: number }

export interface StudioRun {
	run_id: string;
	run_length: RunLength;
	engine: 'PRODUCT_3R' | 'FL10_10R' | 'HARDWARE_DEMO';
	origin: RunOrigin;
	run_type: 'LIVE_RUN' | 'REPLAY';
	algorithm: string;
	secagg_mode: string;
	source_mode: RunSourceMode;
	/** Source mode LIVE_MONITORED_SITE_00 only: which canonical cohort site (0..7) was genuinely live-monitored (0 = SITE_00, the original behaviour). */
	monitored_site?: number | null;
	/** Source mode LIVE_MONITORED_SITE_00 only: the History monitoring session whose regenerated windows were that client's data (null = the site was monitored live). */
	signal_session_id?: string | null;
	/** Which synthetic cohort the run chose (absent on older runs = ORIGINAL, the frozen cohort). */
	cohort?: CohortId;
	cohort_label?: string;
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
export interface StudioSpec { id: string; title: string; caption: string; sources: string[]; group: string; synthetic_label: string; note: string | null; availability: 'AVAILABLE' | 'PARTIAL' | 'PENDING' | 'NOT_APPLICABLE'; availability_detail: string; views: StudioSpecView[] }
export interface StudioFigures { run_id: string; revision: number | null; selected_round: number | null; source_label: string; specs: Record<string, StudioSpec> }
export interface StudioTable { id: string; title: string; columns: string[]; rows: unknown[][]; caption: string; sources: string[]; synthetic_label: string; availability: 'AVAILABLE' | 'PENDING' | 'NOT_APPLICABLE' }
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

export interface StudioRunChoice { run_length: RunLength; source_mode: SourceMode; monitored_site?: number; signal_session_id?: string; initialisation?: Initialisation; algorithm?: 'FEDAVG' | 'FEDPROX'; secagg_mode?: 'PLAIN' | 'SECAGG_SHADOW'; cohort?: CohortId; candidate_id?: string }

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

export interface HardwareStartingModel { id: 'FRESH_SEEDED' | 'WARM_START' | 'MODEL_V2_FINAL' | 'CANDIDATE'; label: string; available: boolean; reason: string | null; note?: string | null }
/** What a pretrained-V2 run could use from the chosen recorded sessions (resample + the unchanged PREPROC_V1 quality gate). */
export interface HardwareV2Preview { sessions: { session_id: string; readings: number; windows: number; usable: number; train: number; holdout: number; by_quality: Record<string, number>; excluded_reasons: Record<string, number> }[]; train_windows: number; holdout_windows: number; min_train_windows: number; min_holdout_windows: number; eligible: boolean; reason: string | null; assumptions: Record<string, unknown> }
