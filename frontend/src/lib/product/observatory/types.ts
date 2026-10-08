import { array, bool, fields, integer, literal, nullable, number, object, string } from '../evidence-validation';

export interface ScenarioInfo {
	scenario_id: string; duration_s: number; window_count: number;
	source_kind: 'SYNTHETIC_VIRTUAL_WEARABLE';
	trace_classification: 'DETERMINISTIC_LOCAL_RECONSTRUCTION';
}
export interface CaptureArm {
	session_id: string; window_index: number;
	status: 'ARMED_BEFORE_START'; storage: 'BOUNDED_IN_MEMORY_ONLY';
}
export function parseCaptureArm(value: unknown): CaptureArm {
	const o = object(value, 'capture_arm');
	fields(o, ['session_id','window_index','status','storage'], 'capture_arm');
	return { session_id: string(o.session_id, 'capture_arm.session_id'),
		window_index: integer(o.window_index, 'capture_arm.window_index'),
		status: literal(o.status, 'ARMED_BEFORE_START', 'capture_arm.status'),
		storage: literal(o.storage, 'BOUNDED_IN_MEMORY_ONLY', 'capture_arm.storage') };
}
export function parseScenarioList(value: unknown): ScenarioInfo[] {
	return array(value, (entry, label) => {
		const o = object(entry, label);
		fields(o, ['scenario_id','duration_s','window_count','source_kind','trace_classification'], label);
		return { scenario_id: string(o.scenario_id, `${label}.scenario_id`),
			duration_s: integer(o.duration_s, `${label}.duration_s`),
			window_count: integer(o.window_count, `${label}.window_count`),
			source_kind: literal(o.source_kind, 'SYNTHETIC_VIRTUAL_WEARABLE', `${label}.source_kind`),
			trace_classification: literal(o.trace_classification, 'DETERMINISTIC_LOCAL_RECONSTRUCTION', `${label}.trace_classification`) };
	}, 'scenarios');
}

export interface SignalPoint { timestamp_us: number; value: number | null; source_index: number | null }
export interface SignalStage {
	stage_id: string; unit: string; sample_rate_hz: number;
	actual_point_count: number; displayed_point_count: number; display_is_decimated: boolean;
	points: SignalPoint[];
}
export interface GapTrace {
	kind: 'SHORT' | 'LONG'; first_missing_index: number; last_missing_index: number;
	missing_count: number; duration_ms: number; fill_count: number;
	previous_segment_id: number; next_segment_id: number; quality_requirement: string;
}
export interface NormalizationTrace {
	status: 'RECONSTRUCTED_MODEL_INPUT' | 'NOT_APPLIED_UNUSABLE'; identity: string;
	mean: number | null; std: number | null; epsilon: number;
	shape: number[] | null; dtype: string | null; tensor_sha256: string | null;
}
export interface PersistedInference {
	model_id: string | null; calibration_domain: string | null;
	raw_probability: number | null; source_domain_calibrated_probability: number | null;
	threshold: number | null; monitoring_state: string; ecg_quality: string;
	probability_role: 'RESEARCH_TECHNICAL_METADATA';
}
export interface WindowTrace {
	trace_version: 'NHM_PIPELINE_TRACE_V1';
	classification: 'DETERMINISTIC_LOCAL_RECONSTRUCTION' | 'CAPTURED_LIVE_PREPROCESSING';
	source_kind: 'SYNTHETIC_VIRTUAL_WEARABLE';
	scenario_id: string; session_id: string | null; window_index: number; window_id: string;
	left_timestamp_us: number; right_timestamp_us: number;
	source_rate_hz: number; target_rate_hz: number; window_sample_count: number; cadence_us: number;
	quality_state: string; quality_reasons: string[]; missing_slots: number; context_available: boolean;
	gaps: GapTrace[]; stages: SignalStage[]; normalization: NormalizationTrace;
	persisted_inference: PersistedInference | null; inference_evidence_status: string;
	claim_boundary: string; limitations: string[];
}

function oneOf<T extends string>(value: unknown, choices: readonly T[], label: string): T {
	const found = string(value, label);
	if (!choices.includes(found as T)) throw new Error(`MALFORMED_EVIDENCE:${label}`);
	return found as T;
}
function point(value: unknown, label: string): SignalPoint {
	const o = object(value, label); fields(o, ['timestamp_us','value','source_index'], label);
	return { timestamp_us: integer(o.timestamp_us, `${label}.timestamp_us`),
		value: nullable(o.value, number, `${label}.value`),
		source_index: nullable(o.source_index, integer, `${label}.source_index`) };
}
function stage(value: unknown, label: string): SignalStage {
	const o = object(value, label);
	fields(o, ['stage_id','unit','sample_rate_hz','actual_point_count','displayed_point_count','display_is_decimated','points'], label);
	const points = array(o.points, point, `${label}.points`);
	const displayed = integer(o.displayed_point_count, `${label}.displayed_point_count`);
	const actual = integer(o.actual_point_count, `${label}.actual_point_count`);
	if (points.length !== displayed || displayed > 1200 || actual < displayed)
		throw new Error(`MALFORMED_EVIDENCE:${label}:bound`);
	return { stage_id: string(o.stage_id, `${label}.stage_id`), unit: string(o.unit, `${label}.unit`),
		sample_rate_hz: integer(o.sample_rate_hz, `${label}.sample_rate_hz`), actual_point_count: actual,
		displayed_point_count: displayed,
		display_is_decimated: bool(o.display_is_decimated, `${label}.display_is_decimated`), points };
}
export { stage as parseSignalStage };
function gap(value: unknown, label: string): GapTrace {
	const o = object(value, label);
	fields(o, ['kind','first_missing_index','last_missing_index','missing_count','duration_ms','fill_count',
		'previous_segment_id','next_segment_id','quality_requirement'], label);
	return { kind: oneOf(o.kind, ['SHORT','LONG'], `${label}.kind`),
		first_missing_index: integer(o.first_missing_index, `${label}.first_missing_index`),
		last_missing_index: integer(o.last_missing_index, `${label}.last_missing_index`),
		missing_count: integer(o.missing_count, `${label}.missing_count`),
		duration_ms: number(o.duration_ms, `${label}.duration_ms`),
		fill_count: integer(o.fill_count, `${label}.fill_count`),
		previous_segment_id: integer(o.previous_segment_id, `${label}.previous_segment_id`),
		next_segment_id: integer(o.next_segment_id, `${label}.next_segment_id`),
		quality_requirement: string(o.quality_requirement, `${label}.quality_requirement`) };
}
function normalization(value: unknown): NormalizationTrace {
	const o = object(value, 'normalization');
	fields(o, ['status','identity','mean','std','epsilon','shape','dtype','tensor_sha256'], 'normalization');
	return { status: oneOf(o.status, ['RECONSTRUCTED_MODEL_INPUT','NOT_APPLIED_UNUSABLE'], 'normalization.status'),
		identity: string(o.identity, 'normalization.identity'),
		mean: nullable(o.mean, number, 'normalization.mean'), std: nullable(o.std, number, 'normalization.std'),
		epsilon: number(o.epsilon, 'normalization.epsilon'),
		shape: nullable(o.shape, (v, l) => array(v, integer, l), 'normalization.shape'),
		dtype: nullable(o.dtype, string, 'normalization.dtype'),
		tensor_sha256: nullable(o.tensor_sha256, string, 'normalization.tensor_sha256') };
}
function inference(value: unknown): PersistedInference {
	const o = object(value, 'persisted_inference');
	fields(o, ['model_id','calibration_domain','raw_probability','source_domain_calibrated_probability',
		'threshold','monitoring_state','ecg_quality','probability_role'], 'persisted_inference');
	return { model_id: nullable(o.model_id, string, 'model_id'),
		calibration_domain: nullable(o.calibration_domain, string, 'calibration_domain'),
		raw_probability: nullable(o.raw_probability, number, 'raw_probability'),
		source_domain_calibrated_probability: nullable(o.source_domain_calibrated_probability, number, 'calibrated_probability'),
		threshold: nullable(o.threshold, number, 'threshold'), monitoring_state: string(o.monitoring_state, 'monitoring_state'),
		ecg_quality: string(o.ecg_quality, 'ecg_quality'),
		probability_role: literal(o.probability_role, 'RESEARCH_TECHNICAL_METADATA', 'probability_role') };
}

export function parseWindowTrace(value: unknown): WindowTrace {
	const o = object(value, 'window_trace');
	fields(o, ['trace_version','classification','source_kind','scenario_id','session_id','window_index','window_id',
		'left_timestamp_us','right_timestamp_us','source_rate_hz','target_rate_hz','window_sample_count',
		'cadence_us','quality_state','quality_reasons','missing_slots','context_available','gaps','stages','normalization',
		'persisted_inference','inference_evidence_status','claim_boundary','limitations'], 'window_trace');
	const stages = array(o.stages, stage, 'stages');
	if (new Set(stages.map((s) => s.stage_id)).size !== stages.length) throw new Error('MALFORMED_EVIDENCE:duplicate_stage');
	const left = integer(o.left_timestamp_us, 'left_timestamp_us');
	const right = integer(o.right_timestamp_us, 'right_timestamp_us');
	if (right - left !== 10_000_000) throw new Error('MALFORMED_EVIDENCE:window_duration');
	return { trace_version: literal(o.trace_version, 'NHM_PIPELINE_TRACE_V1', 'trace_version'),
		classification: oneOf(o.classification,
			['DETERMINISTIC_LOCAL_RECONSTRUCTION', 'CAPTURED_LIVE_PREPROCESSING'], 'classification'),
		source_kind: literal(o.source_kind, 'SYNTHETIC_VIRTUAL_WEARABLE', 'source_kind'),
		scenario_id: string(o.scenario_id, 'scenario_id'), session_id: nullable(o.session_id, string, 'session_id'),
		window_index: integer(o.window_index, 'window_index'), window_id: string(o.window_id, 'window_id'),
		left_timestamp_us: left, right_timestamp_us: right,
		source_rate_hz: integer(o.source_rate_hz, 'source_rate_hz'),
		target_rate_hz: integer(o.target_rate_hz, 'target_rate_hz'),
		window_sample_count: integer(o.window_sample_count, 'window_sample_count'),
		cadence_us: integer(o.cadence_us, 'cadence_us'),
		quality_state: string(o.quality_state, 'quality_state'),
		quality_reasons: array(o.quality_reasons, string, 'quality_reasons'),
		missing_slots: integer(o.missing_slots, 'missing_slots'),
		context_available: bool(o.context_available, 'context_available'),
		gaps: array(o.gaps, gap, 'gaps'), stages, normalization: normalization(o.normalization),
		persisted_inference: nullable(o.persisted_inference, inference, 'persisted_inference'),
		inference_evidence_status: string(o.inference_evidence_status, 'inference_evidence_status'),
		claim_boundary: string(o.claim_boundary, 'claim_boundary'), limitations: array(o.limitations, string, 'limitations') };
}

export interface ScenarioTimeline {
	scenario_id: string; duration_s: number; time_basis: string;
	segments: { name: string; start_s: number; end_s: number; ecg_fault: string | null; context_mode: string }[];
	connection_events: string[]; window_right_edges_s: number[]; window_length_s: number; window_cadence_s: number;
}
export function parseScenarioTimeline(value: unknown): ScenarioTimeline {
	const bad = (): never => { throw new Error('MALFORMED_OBSERVATORY_TIMELINE'); };
	const r = (value ?? bad()) as Record<string, unknown>;
	if (r.classification !== 'FROZEN_SCENARIO_DEFINITION' || r.time_basis !== 'SIMULATED_SOURCE_TIME_NOT_WALL_CLOCK') bad();
	const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : bad());
	const n = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : bad());
	const t = (v: unknown): string => (typeof v === 'string' ? v : bad());
	return { scenario_id: t(r.scenario_id), duration_s: n(r.duration_s), time_basis: t(r.time_basis),
		segments: list(r.segments).map((x) => { const g = x as Record<string, unknown>; return { name: t(g.name), start_s: n(g.start_s), end_s: n(g.end_s), ecg_fault: g.ecg_fault === null ? null : t(g.ecg_fault), context_mode: t(g.context_mode) }; }),
		connection_events: list(r.connection_events).map(t), window_right_edges_s: list(r.window_right_edges_s).map(n), window_length_s: n(r.window_length_s), window_cadence_s: n(r.window_cadence_s) };
}
