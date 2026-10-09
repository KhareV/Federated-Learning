// NHM_UNIFIED_LIVE_FEDERATION_STUDIO_001 -- typed, fail-closed models of the Studio REST payloads. Values are validated and passed through; nothing is computed here.
export const RUN_LENGTHS = [3, 10] as const;
export type RunLength = (typeof RUN_LENGTHS)[number];
export type EvaluationStatus = 'QUEUED' | 'EVALUATING' | 'COMPLETED' | 'FAILED';
export type RoundEvalStatus = EvaluationStatus | 'NOT_SUBMITTED';
export type RunOrigin = 'LIVE' | 'REPLAY' | 'RECORDED';
export type SourceMode = 'CANONICAL_SYNTHETIC' | 'LIVE_MONITORED_SITE_00';
export type ExportStatus = 'NOT_STARTED' | 'PREPARING' | 'READY' | 'FAILED';

export interface StudioCapabilities {
	studio_id: string;
	run_lengths: number[];
	default_run_length: number;
	ten_round: { available: boolean; source_modes: SourceMode[]; algorithms: string[]; aggregation_modes: string[]; unsupported: Record<string, string>; expected_updates: number };
	three_round: { available: boolean; expected_updates: number };
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

export interface StudioRunChoice { run_length: RunLength; source_mode: SourceMode }
