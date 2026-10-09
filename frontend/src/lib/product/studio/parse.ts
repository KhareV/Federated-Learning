// Fail-closed parsers for the Studio REST payloads (no value is cast blindly; a malformed or foreign payload throws).
import type { BaseModel, GenCohort, GenCurves, GenInterval, GenPair, GenParticipants, GenRecord, GenRound, Generalisation, Initialisation, StudioOverview, EvalRecord, EvalRoundDetail, EvalSummary, EvaluationAvailability, RoundDetail, StudioCapabilities, StudioExports, StudioFigures, StudioRun, StudioSpec, StudioTable, StudioTables } from './types';

type Rec = Record<string, unknown>;
export class StudioParseError extends Error {
	constructor(readonly reason: string) { super(reason); this.name = 'StudioParseError'; }
}
const bad = (reason: string): never => { throw new StudioParseError(reason); };
const obj = (v: unknown, n: string): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : bad(`NOT_AN_OBJECT:${n}`));
const arr = (v: unknown, n: string): unknown[] => (Array.isArray(v) ? v : bad(`NOT_AN_ARRAY:${n}`));
const str = (v: unknown, n: string): string => (typeof v === 'string' ? v : bad(`BAD_STRING:${n}`));
const strOrNull = (v: unknown, n: string): string | null => (v === null || v === undefined ? null : str(v, n));
const num = (v: unknown, n: string): number => (typeof v === 'number' && Number.isFinite(v) ? v : bad(`BAD_NUMBER:${n}`));
const numOrNull = (v: unknown, n: string): number | null => (v === null || v === undefined ? null : num(v, n));
const int = (v: unknown, n: string): number => (typeof v === 'number' && Number.isInteger(v) ? v : bad(`BAD_INT:${n}`));
function oneOf<T extends string>(v: unknown, allowed: readonly T[], n: string): T {
	return typeof v === 'string' && (allowed as readonly string[]).includes(v) ? (v as T) : bad(`BAD_ENUM:${n}`);
}
const finiteOrNull = (v: unknown): boolean => v === null || (typeof v === 'number' && Number.isFinite(v));

const STATUSES = ['QUEUED', 'EVALUATING', 'COMPLETED', 'FAILED'] as const;
const ROUND_STATUSES = [...STATUSES, 'NOT_SUBMITTED'] as const;
const DIGEST = /^[0-9a-f]{64}$/;
const INITS = ['FL_INIT_V2', 'MODEL_V2_FINAL'] as const;

function availability(raw: unknown): EvaluationAvailability {
	const r = obj(raw, 'evaluation');
	return { available: r.available === true, source: oneOf(r.source, ['LIVE', 'RECORDED', 'RECORDED_FROM_SOURCE_RUN'] as const, 'source'), evaluation_run_id: str(r.evaluation_run_id, 'evaluation_run_id'),
		reason: strOrNull(r.reason, 'reason'), revision: int(r.revision, 'revision') };
}

export function parseCapabilities(value: unknown): StudioCapabilities {
	const r = obj(value, 'capabilities'), t = obj(r.ten_round, 'ten_round'), h = obj(r.three_round, 'three_round'), e = obj(r.evaluation, 'evaluation');
	return { studio_id: str(r.studio_id, 'studio_id'), run_lengths: arr(r.run_lengths, 'run_lengths').map((x) => int(x, 'run_length')), default_run_length: int(r.default_run_length, 'default'),
		ten_round: { available: t.available === true, initialisations: Array.isArray(t.initialisations) ? t.initialisations.map((i) => { const o = obj(i, 'initialisation'); return { id: oneOf(o.id, INITS, 'initialisation'), label: str(o.label, 'label'), default: o.default === true }; }) : undefined, source_modes: arr(t.source_modes, 'modes').map((m) => oneOf(m, ['CANONICAL_SYNTHETIC', 'LIVE_MONITORED_SITE_00'] as const, 'mode')), algorithms: arr(t.algorithms, 'algorithms').map((x) => str(x, 'algorithm')),
			aggregation_modes: arr(t.aggregation_modes, 'agg').map((x) => str(x, 'agg')), unsupported: Object.fromEntries(Object.entries(obj(t.unsupported, 'unsupported')).map(([k, v]) => [k, str(v, 'why')])), expected_updates: int(t.expected_updates, 'expected') },
		three_round: { available: h.available === true, expected_updates: int(h.expected_updates, 'expected') },
		generalisation: r.generalisation ? { cohort_id: str(obj(r.generalisation, 'generalisation').cohort_id, 'cohort_id'), label: str(obj(r.generalisation, 'generalisation').label, 'label'), claim_boundary: str(obj(r.generalisation, 'generalisation').claim_boundary, 'claim_boundary'), baseline: str(obj(r.generalisation, 'generalisation').baseline, 'baseline') } : undefined,
		evaluation: { observer_id: str(e.observer_id, 'observer'), protocol_id: str(e.protocol_id, 'protocol'), threshold: num(e.threshold, 'threshold'), calibration: str(e.calibration, 'calibration'), cohort_use: str(e.cohort_use, 'cohort_use'),
			cohort_use_detail: str(e.cohort_use_detail, 'cohort_use_detail'), claim_boundary: str(e.claim_boundary, 'claim_boundary') } };
}

function baseModel(raw: unknown): BaseModel | null {
	if (raw === null || raw === undefined) return null;
	const b = obj(raw, 'base_model');
	return { model_id: oneOf(b.model_id, INITS, 'base model') as Initialisation, label: str(b.label, 'base label'), state_sha256: strOrNull(b.state_sha256, 'state_sha256'), checkpoint_sha256: strOrNull(b.checkpoint_sha256, 'checkpoint_sha256'),
		state_entries: numOrNull(b.state_entries, 'state_entries'), architecture_id: strOrNull(b.architecture_id, 'architecture_id'), training_target_of_checkpoint: strOrNull(b.training_target_of_checkpoint, 'target') };
}

export function parseStudioRun(value: unknown): StudioRun {
	const r = obj(value, 'run');
	const length = int(r.run_length, 'run_length');
	if (length !== 3 && length !== 10) bad('BAD_RUN_LENGTH');
	const cand = r.candidate === null || r.candidate === undefined ? null : obj(r.candidate, 'candidate');
	const fail = r.failure === null || r.failure === undefined ? null : obj(r.failure, 'failure');
	if (cand && (cand.promoted !== false || cand.deployed !== false)) bad('CANDIDATE_MUST_NOT_BE_PROMOTED_OR_DEPLOYED');
	return { run_id: str(r.run_id, 'run_id'), run_length: length as 3 | 10, engine: oneOf(r.engine, ['PRODUCT_3R', 'FL10_10R'] as const, 'engine'), origin: oneOf(r.origin, ['LIVE', 'REPLAY', 'RECORDED'] as const, 'origin'),
		run_type: oneOf(r.run_type, ['LIVE_RUN', 'REPLAY'] as const, 'run_type'), algorithm: str(r.algorithm, 'algorithm'), secagg_mode: str(r.secagg_mode, 'secagg_mode'),
		source_mode: oneOf(r.source_mode, ['CANONICAL_SYNTHETIC', 'LIVE_MONITORED_SITE_00'] as const, 'source_mode'), status: oneOf(r.status, ['CREATED', 'RUNNING', 'COMPLETED', 'FAILED'] as const, 'status'), phase: str(r.phase, 'phase'),
		current_round: int(r.current_round, 'current_round'), planned_rounds: int(r.planned_rounds, 'planned_rounds'), client_ids: arr(r.client_ids, 'client_ids').map((c) => str(c, 'client')),
		candidate: cand ? { candidate_id: strOrNull(cand.candidate_id, 'candidate_id'), state_sha256: strOrNull(cand.state_sha256, 'state_sha256'), promoted: false, deployed: false, label: typeof cand.label === 'string' ? cand.label : undefined } : null,
		failure: fail ? { code: str(fail.code, 'code'), message: str(fail.message, 'message') } : null, label: str(r.label, 'label'), base_model: baseModel(r.base_model), source_label: str(r.source_label, 'source_label'), replay_of: strOrNull(r.replay_of, 'replay_of'),
		evaluation: availability(r.evaluation), export_status: oneOf(r.export_status, ['NOT_STARTED', 'PREPARING', 'READY', 'FAILED'] as const, 'export_status'), created_at: strOrNull(r.created_at, 'created_at') };
}
export const parseStudioRuns = (value: unknown): StudioRun[] => arr(value, 'runs').map(parseStudioRun);

function metrics(raw: unknown, n: string): Record<string, never> {
	const m = obj(raw, n);
	for (const [k, v] of Object.entries(m)) if (typeof v === 'number' && !Number.isFinite(v)) bad(`NONFINITE_METRIC:${k}`);
	return m as Record<string, never>;
}

export function parseEvalRecord(value: unknown): EvalRecord {
	const r = obj(value, 'record');
	const status = oneOf(r.evaluation_status, STATUSES, 'evaluation_status');
	const fail = r.failure === null || r.failure === undefined ? null : obj(r.failure, 'failure');
	const result = r.metric_result === null || r.metric_result === undefined ? null : metrics(r.metric_result, 'metric_result');
	const confusion = r.confusion_counts === null || r.confusion_counts === undefined ? null : Object.fromEntries(Object.entries(obj(r.confusion_counts, 'confusion')).map(([k, v]) => [k, int(v, k)]));
	if ((status === 'COMPLETED') !== (result !== null)) bad('METRICS_REQUIRED_IFF_COMPLETED');     // a queued/failed round never carries numbers
	if ((status === 'FAILED') !== (fail !== null)) bad('FAILURE_REQUIRED_IFF_FAILED');
	if (!DIGEST.test(str(r.global_state_digest, 'digest'))) bad('BAD_STATE_DIGEST');
	const ref = (v: unknown, n: string) => (v === null || v === undefined ? null : { path: str(obj(v, n).path, n), sha256: str(obj(v, n).sha256, n) });
	return { run_id: str(r.run_id, 'run_id'), run_length: int(r.run_length, 'run_length'), round_id: int(r.round_id, 'round_id'), global_state_digest: r.global_state_digest as string, candidate_id: strOrNull(r.candidate_id, 'candidate_id'),
		cohort_id: str(r.cohort_id, 'cohort_id'), cohort_use: str(r.cohort_use, 'cohort_use'), evaluation_protocol_id: str(r.evaluation_protocol_id, 'protocol'), evaluation_status: status,
		evaluation_queued_at: strOrNull(r.evaluation_queued_at, 'queued'), evaluation_started_at: strOrNull(r.evaluation_started_at, 'started'), evaluation_completed_at: strOrNull(r.evaluation_completed_at, 'completed'),
		failure: fail ? { code: str(fail.code, 'code'), message: str(fail.message, 'message') } : null, threshold: num(r.threshold, 'threshold'), calibration: str(r.calibration, 'calibration'), windows: numOrNull(r.windows, 'windows'),
		metric_result: result, confusion_counts: confusion, prediction_artifact_reference: ref(r.prediction_artifact_reference, 'prediction'), curve_artifact_reference: ref(r.curve_artifact_reference, 'curve'),
		source_digest: strOrNull(r.source_digest, 'source_digest'), claim_boundary: typeof r.claim_boundary === 'string' ? r.claim_boundary : undefined, source: r.source === 'RECORDED' ? 'RECORDED' : undefined };
}

export function parseEvalSummary(value: unknown): EvalSummary {
	const r = obj(value, 'summary'), c = obj(r.comparison, 'comparison');
	const length = int(r.run_length, 'run_length');
	if (length !== 3 && length !== 10) bad('BAD_RUN_LENGTH');
	const records = arr(r.records, 'records').map(parseEvalRecord);
	for (const rec of records) if (rec.run_id !== r.run_id && !rec.source) bad('FOREIGN_RECORD_RUN_ID');
	return { run_id: str(r.run_id, 'run_id'), run_length: length as 3 | 10, evaluation: availability(r.evaluation), records, rounds_expected: arr(r.rounds_expected, 'rounds_expected').map((x) => int(x, 'round')),
		comparison: { comparator_round: int(c.comparator_round, 'comparator'), endpoint_round: int(c.endpoint_round, 'endpoint'), paired_available: c.paired_available === true }, evaluation_protocol_id: str(r.evaluation_protocol_id, 'protocol'),
		observer_id: str(r.observer_id, 'observer'), cohort_use: str(r.cohort_use, 'cohort_use'), cohort_use_detail: str(r.cohort_use_detail, 'detail'), claim_boundary: str(r.claim_boundary, 'claim_boundary'), threshold: num(r.threshold, 'threshold'),
		calibration: str(r.calibration, 'calibration'), source_label: str(r.source_label, 'source_label'), run_status: str(r.run_status, 'run_status'), revision: int(r.revision, 'revision') };
}

export function parseEvalRound(value: unknown): EvalRoundDetail {
	const r = obj(value, 'round');
	const status = oneOf(r.evaluation_status, ROUND_STATUSES, 'evaluation_status');
	if (status === 'NOT_SUBMITTED') return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), evaluation_status: status, reason: typeof r.reason === 'string' ? r.reason : undefined };
	const base = parseEvalRecord(r);
	const participants = r.participant_metrics === null || r.participant_metrics === undefined ? undefined : Object.fromEntries(Object.entries(obj(r.participant_metrics, 'participants')).map(([k, v]) => [k, metrics(v, k)]));
	const curves = r.curves === null || r.curves === undefined ? null : obj(r.curves, 'curves');
	const checkCurve = (c: unknown) => arr(c, 'curve').map((p) => { const point = arr(p, 'point'); if (point.length !== 2 || !point.every((x) => typeof x === 'number' && Number.isFinite(x))) bad('BAD_CURVE_POINT'); return point as number[]; });
	const summary = r.participant_summary ? obj(r.participant_summary, 'participant_summary') : null;
	return { ...base, participant_metrics: participants, participant_summary: summary ? { participant_macro_F1: numOrNull(summary.participant_macro_F1, 'macro'), participants_defined: int(summary.participants_defined, 'defined'), participants_undefined: int(summary.participants_undefined, 'undefined') } : undefined,
		curves: curves ? { roc: checkCurve(curves.roc), pr: checkCurve(curves.pr) } : null };
}

export function parseSpec(value: unknown): StudioSpec {
	const s = obj(value, 'spec');
	const views = arr(s.views, 'views').map((raw) => {
		const v = obj(raw, 'view');
		for (const series of (Array.isArray(v.series) ? v.series : []) as Rec[]) for (const key of ['y', 'values'] as const) if (key in series) for (const n of arr(series[key], key)) if (!finiteOrNull(n)) bad('NONFINITE_SERIES_VALUE');
		return { ...v, id: str(v.id, 'view id'), label: str(v.label, 'view label'), kind: str(v.kind, 'view kind') };
	});
	return { id: str(s.id, 'id'), title: str(s.title, 'title'), caption: str(s.caption, 'caption'), sources: arr(s.sources, 'sources').map((x) => str(x, 'source')), group: str(s.group, 'group'), synthetic_label: str(s.synthetic_label, 'synthetic_label'),
		note: typeof s.note === 'string' ? s.note : null, availability: oneOf(s.availability, ['AVAILABLE', 'PARTIAL', 'PENDING'] as const, 'availability'), availability_detail: str(s.availability_detail, 'availability_detail'), views } as StudioSpec;
}

export function parseFigures(value: unknown): StudioFigures {
	const r = obj(value, 'figures');
	const specs = Object.fromEntries(Object.entries(obj(r.specs, 'specs')).map(([k, v]) => [k, parseSpec(v)]));
	if (Object.keys(specs).length !== 20) bad('FIGURE_INVENTORY_INCOMPLETE');
	return { run_id: str(r.run_id, 'run_id'), revision: numOrNull(r.revision, 'revision'), selected_round: numOrNull(r.selected_round, 'selected_round'), source_label: str(r.source_label, 'source_label'), specs };
}

export function parseTables(value: unknown): StudioTables {
	const r = obj(value, 'tables');
	const tables: Record<string, StudioTable> = {};
	for (const [id, raw] of Object.entries(obj(r.tables, 'tables'))) {
		const t = obj(raw, id), columns = arr(t.columns, 'columns').map((c) => str(c, 'column'));
		const rows = arr(t.rows, 'rows').map((row) => { const cells = arr(row, 'row'); if (cells.length !== columns.length) bad(`ROW_WIDTH:${id}`); return cells; });
		tables[id] = { id, title: str(t.title, 'title'), columns, rows, caption: str(t.caption, 'caption'), sources: arr(t.sources, 'sources').map((x) => str(x, 'source')), synthetic_label: str(t.synthetic_label, 'synthetic_label'), availability: oneOf(t.availability, ['AVAILABLE', 'PENDING'] as const, 'availability') };
	}
	if (Object.keys(tables).length !== 12) bad('TABLE_INVENTORY_INCOMPLETE');
	return { run_id: str(r.run_id, 'run_id'), revision: numOrNull(r.revision, 'revision'), source_label: str(r.source_label, 'source_label'), tables };
}

function entries(raw: unknown): Record<string, Record<string, { path: string; sha256: string; rows?: number }>> {
	return Object.fromEntries(Object.entries(obj(raw, 'exports')).map(([id, files]) => [id, Object.fromEntries(Object.entries(obj(files, id)).map(([fmt, e]) => [fmt, { path: str(obj(e, fmt).path, 'path'), sha256: str(obj(e, fmt).sha256, 'sha256'),
		rows: typeof obj(e, fmt).rows === 'number' ? (obj(e, fmt).rows as number) : undefined }]))]));
}

export function parseExports(value: unknown): StudioExports {
	const r = obj(value, 'exports');
	const status = oneOf(r.status, ['NOT_STARTED', 'PREPARING', 'READY', 'FAILED'] as const, 'status');
	return { status, message: typeof r.message === 'string' ? r.message : undefined, run_id: str(r.run_id, 'run_id'), figures: r.figures ? entries(r.figures) : undefined, tables: r.tables ? entries(r.tables) : undefined,
		data: r.data ? entries(r.data) : undefined, source_label: typeof r.source_label === 'string' ? r.source_label : undefined, cohort_use: typeof r.cohort_use === 'string' ? r.cohort_use : undefined };
}

export function parseOverview(value: unknown): StudioOverview {
	const r = obj(value, 'overview');
	const bridge = obj(r.scientific_bridge, 'scientific_bridge');
	const length = int(r.run_length, 'run_length');
	if (length !== 3 && length !== 10) bad('BAD_RUN_LENGTH');
	arr(obj(r.protocol, 'protocol').interpretation_boundaries ?? [], 'boundaries').map((x) => str(x, 'boundary'));
	arr(bridge.comparability_rows, 'rows').map((x) => obj(x, 'bridge row'));
	return { ...r, run_id: str(r.run_id, 'run_id'), run_length: length, source_label: str(r.source_label, 'source_label'), synthetic_label: str(r.synthetic_label, 'synthetic_label'), live_label: strOrNull(r.live_label, 'live_label'),
		run: obj(r.run, 'run'), protocol: obj(r.protocol, 'protocol'), evaluation: obj(r.evaluation, 'evaluation'), rounds: arr(r.rounds, 'rounds').map((x) => obj(x, 'round')),
		state_progression: obj(r.state_progression, 'state_progression'), monitoring_link: r.monitoring_link ? obj(r.monitoring_link, 'monitoring_link') : null,
		scientific_bridge: { comparability_rows: bridge.comparability_rows, verdict: str(bridge.verdict, 'verdict'), limitations: arr(bridge.limitations, 'limitations').map((x) => str(x, 'limitation')), route: str(bridge.route, 'route'), note: str(bridge.note, 'note') } } as unknown as StudioOverview;
}

export function parseRoundDetail(value: unknown): RoundDetail {
	const r = obj(value, 'round detail');
	return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), committed: r.committed === true, round: r.round ? obj(r.round, 'round') : null, client_rounds: arr(r.client_rounds, 'client_rounds').map((x) => obj(x, 'client round')),
		batches: arr(r.batches, 'batches').map((x) => obj(x, 'batch')), state: r.state ? obj(r.state, 'state') : null };
}

// ---- Generalisation ------------------------------------------------------------------------------------------------------------
function genRecord(value: unknown): GenRecord {
	const record = parseEvalRecord(value);
	const subject = oneOf(obj(value, 'record').subject, ['FL_ROUND', 'FROZEN_V2_BASELINE'] as const, 'subject');
	return { ...record, subject };
}
const interval = (v: unknown): GenInterval => { const o = obj(v, 'interval'); return { lower: numOrNull(o.lower, 'lower'), upper: numOrNull(o.upper, 'upper'), valid_replicates: int(o.valid_replicates, 'valid') }; };
function genPair(value: unknown): GenPair {
	const p = obj(value, 'pair');
	const m = Object.fromEntries(Object.entries(obj(p.metrics, 'pair metrics')).map(([k, raw]) => {
		const o = obj(raw, k);
		return [k, { A_point: numOrNull(o.A_point, 'A'), B_point: numOrNull(o.B_point, 'B'), difference_point: numOrNull(o.difference_point, 'difference'), difference_interval: interval(o.difference_interval), invalid_replicates: int(o.invalid_replicates, 'invalid') }];
	}));
	return { clusters: int(p.clusters, 'clusters'), replicates: int(p.replicates, 'replicates'), seed: int(p.seed, 'seed'), method: str(p.method, 'method'), multiplicity: str(p.multiplicity, 'multiplicity'), metrics: m, identical_predictions: p.identical_predictions === true };
}
function genCohort(value: unknown): GenCohort {
	const c = obj(value, 'cohort');
	return { cohort_id: str(c.cohort_id, 'cohort_id'), label: str(c.label, 'label'), detail: str(c.detail, 'detail'), participants: int(c.participants, 'participants'), windows: int(c.windows, 'windows'), positive_windows: int(c.positive_windows, 'positive'),
		participant_ids: arr(c.participant_ids, 'ids').map((x) => str(x, 'id')), site_conditions: arr(c.site_conditions, 'sites').map((x) => str(x, 'site')), manifest_sha256: strOrNull(c.manifest_sha256, 'manifest'),
		separation: c.separation ? (obj(c.separation, 'separation') as GenCohort['separation']) : null, separation_note: strOrNull(c.separation_note, 'note') };
}
export function parseGeneralisation(value: unknown): Generalisation {
	const r = obj(value, 'generalisation');
	if (r.schema_version !== 'STUDIO_GENERALISATION_V1') bad('BAD_GENERALISATION_SCHEMA');
	const rounds: GenRound[] = arr(r.rounds, 'rounds').map((raw) => {
		const o = obj(raw, 'round');
		const record = o.record ? genRecord(o.record) : null;
		if (record && record.run_id !== r.run_id) bad('FOREIGN_GENERALISATION_RECORD');
		return { round_id: int(o.round_id, 'round_id'), record, paired_vs_v2: o.paired_vs_v2 ? genPair(o.paired_vs_v2) : null };
	});
	const b = obj(r.baseline, 'baseline'), i = obj(r.integrity, 'integrity');
	const baseline = b.record ? genRecord(b.record) : null;
	if (baseline && baseline.subject !== 'FROZEN_V2_BASELINE') bad('BASELINE_SUBJECT_MISMATCH');
	const triple = (v: unknown): boolean | null => (v === null || v === undefined ? null : v === true ? true : v === false ? false : bad('BAD_BOOL'));
	return { schema_version: 'STUDIO_GENERALISATION_V1', run_id: str(r.run_id, 'run_id'), run_length: int(r.run_length, 'run_length'), observer_id: str(r.observer_id, 'observer'), claim_boundary: str(r.claim_boundary, 'claim'),
		threshold: num(r.threshold, 'threshold'), calibration: str(r.calibration, 'calibration'), base_model: baseModel(r.base_model) ?? bad('MISSING_BASE_MODEL'), cohort: genCohort(r.cohort),
		baseline: { label: str(b.label, 'label'), detail: str(b.detail, 'detail'), record: baseline, state_sha256: strOrNull(b.state_sha256, 'state') }, rounds,
		integrity: { r0_digest_equals_frozen_v2: triple(i.r0_digest_equals_frozen_v2), r0_predictions_equal_frozen_v2: triple(i.r0_predictions_equal_frozen_v2) }, metrics_order: arr(r.metrics_order, 'order').map((x) => str(x, 'metric')),
		lower_is_better: arr(r.lower_is_better, 'lower').map((x) => str(x, 'metric')), interpretation: arr(r.interpretation, 'interpretation').map((x) => str(x, 'line')), revision: int(r.revision, 'revision') };
}
const curve = (c: unknown) => arr(c, 'curve').map((p) => { const point = arr(p, 'point'); if (point.length !== 2 || !point.every((x) => typeof x === 'number' && Number.isFinite(x))) bad('BAD_CURVE_POINT'); return point as number[]; });
const curveSet = (v: unknown) => { const o = obj(v, 'curves'); return { roc: curve(o.roc), pr: curve(o.pr) }; };
export function parseGenCurves(value: unknown): GenCurves {
	const r = obj(value, 'gen curves');
	if (r.available !== true) return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), available: false, reason: typeof r.reason === 'string' ? r.reason : undefined };
	return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), available: true, round: curveSet(r.round), baseline: r.baseline ? curveSet(r.baseline) : null };
}
export function parseGenParticipants(value: unknown): GenParticipants {
	const r = obj(value, 'gen participants');
	if (r.available !== true) return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), available: false };
	const set = (v: unknown) => Object.fromEntries(Object.entries(obj(v, 'participants')).map(([k, m]) => [k, metrics(m, k)]));
	return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), available: true, round: set(r.round), baseline: r.baseline ? set(r.baseline) : null };
}
