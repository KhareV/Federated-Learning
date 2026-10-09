// Fail-closed parsers for the Studio REST payloads (no value is cast blindly; a malformed or foreign payload throws).
import type { EvalRecord, EvalRoundDetail, EvalSummary, EvaluationAvailability, RoundDetail, StudioCapabilities, StudioExports, StudioFigures, StudioRun, StudioSpec, StudioTable, StudioTables } from './types';

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

function availability(raw: unknown): EvaluationAvailability {
	const r = obj(raw, 'evaluation');
	return { available: r.available === true, source: oneOf(r.source, ['LIVE', 'RECORDED', 'RECORDED_FROM_SOURCE_RUN'] as const, 'source'), evaluation_run_id: str(r.evaluation_run_id, 'evaluation_run_id'),
		reason: strOrNull(r.reason, 'reason'), revision: int(r.revision, 'revision') };
}

export function parseCapabilities(value: unknown): StudioCapabilities {
	const r = obj(value, 'capabilities'), t = obj(r.ten_round, 'ten_round'), h = obj(r.three_round, 'three_round'), e = obj(r.evaluation, 'evaluation');
	return { studio_id: str(r.studio_id, 'studio_id'), run_lengths: arr(r.run_lengths, 'run_lengths').map((x) => int(x, 'run_length')), default_run_length: int(r.default_run_length, 'default'),
		ten_round: { available: t.available === true, source_modes: arr(t.source_modes, 'modes').map((m) => oneOf(m, ['CANONICAL_SYNTHETIC', 'LIVE_MONITORED_SITE_00'] as const, 'mode')), algorithms: arr(t.algorithms, 'algorithms').map((x) => str(x, 'algorithm')),
			aggregation_modes: arr(t.aggregation_modes, 'agg').map((x) => str(x, 'agg')), unsupported: Object.fromEntries(Object.entries(obj(t.unsupported, 'unsupported')).map(([k, v]) => [k, str(v, 'why')])), expected_updates: int(t.expected_updates, 'expected') },
		three_round: { available: h.available === true, expected_updates: int(h.expected_updates, 'expected') },
		evaluation: { observer_id: str(e.observer_id, 'observer'), protocol_id: str(e.protocol_id, 'protocol'), threshold: num(e.threshold, 'threshold'), calibration: str(e.calibration, 'calibration'), cohort_use: str(e.cohort_use, 'cohort_use'),
			cohort_use_detail: str(e.cohort_use_detail, 'cohort_use_detail'), claim_boundary: str(e.claim_boundary, 'claim_boundary') } };
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
		failure: fail ? { code: str(fail.code, 'code'), message: str(fail.message, 'message') } : null, label: str(r.label, 'label'), source_label: str(r.source_label, 'source_label'), replay_of: strOrNull(r.replay_of, 'replay_of'),
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

export function parseRoundDetail(value: unknown): RoundDetail {
	const r = obj(value, 'round detail');
	return { run_id: str(r.run_id, 'run_id'), round_id: int(r.round_id, 'round_id'), committed: r.committed === true, round: r.round ? obj(r.round, 'round') : null, client_rounds: arr(r.client_rounds, 'client_rounds').map((x) => obj(x, 'client round')),
		batches: arr(r.batches, 'batches').map((x) => obj(x, 'batch')), state: r.state ? obj(r.state, 'state') : null };
}
