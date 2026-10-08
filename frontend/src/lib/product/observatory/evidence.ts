// Typed, fail-closed parsers for the Observatory's FROZEN research-evidence routes. No values are computed here.
type Rec = Record<string, unknown>;
const bad = (): never => { throw new Error('MALFORMED_OBSERVATORY_EVIDENCE'); };
const obj = (v: unknown): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : bad());
const str = (v: unknown): string => (typeof v === 'string' ? v : bad());
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : bad());
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : bad());
const nstr = (v: unknown): string | null => (v === null || v === undefined ? null : str(v));

export interface Interval { lower: number; upper: number }
export interface EvalModel {
	model_id: string; generation: string; algorithm: string; condition: string; mu: number | null;
	checkpoint_sha256: string; development_round: number; point: Record<string, number>;
	ci_95: Record<string, Interval>;
}
export interface EvalComparison { comparison_id: string; family: string; a: string; b: string; delta: Record<string, { point: number; lower: number; upper: number }> }
export interface EvalDataset {
	claim_label: string; clusters: number; windows: number; models: EvalModel[]; comparisons: EvalComparison[];
	bootstrap: { replicates: number; seed: number; rng: string; draws_sha256: string; multiplicity_adjustment: string; p_values: string };
	source: { path: string; sha256: string };
}
export interface FlEval { datasets: Record<string, EvalDataset>; limitations: string[] }

export function parseFlEval(value: unknown): FlEval {
	const root = obj(value);
	if (root.classification !== 'FROZEN_RESEARCH_EVIDENCE') bad();
	const datasets: Record<string, EvalDataset> = {};
	for (const [name, raw] of Object.entries(obj(root.datasets))) {
		const d = obj(raw); const b = obj(d.bootstrap); const s = obj(d.source);
		datasets[name] = {
			claim_label: str(d.claim_label), clusters: num(d.clusters), windows: num(d.windows),
			models: arr(d.models).map((item) => {
				const m = obj(item);
				const point: Record<string, number> = {};
				for (const [k, v] of Object.entries(obj(m.point))) point[k] = num(v);
				const ci: Record<string, Interval> = {};
				for (const [k, v] of Object.entries(obj(m.ci_95))) { const i = obj(v); ci[k] = { lower: num(i.lower), upper: num(i.upper) }; }
				return { model_id: str(m.model_id), generation: str(m.generation), algorithm: str(m.algorithm), condition: str(m.condition),
					mu: m.mu === null ? null : num(m.mu), checkpoint_sha256: str(m.checkpoint_sha256), development_round: num(m.development_round), point, ci_95: ci };
			}),
			comparisons: arr(d.comparisons).map((item) => {
				const c = obj(item); const delta: EvalComparison['delta'] = {};
				for (const [k, v] of Object.entries(obj(c.delta))) { const e = obj(v); delta[k] = { point: num(e.point), lower: num(e.lower), upper: num(e.upper) }; }
				return { comparison_id: str(c.comparison_id), family: str(c.family), a: str(c.a), b: str(c.b), delta };
			}),
			bootstrap: { replicates: num(b.replicates), seed: num(b.seed), rng: str(b.rng), draws_sha256: str(b.draws_sha256),
				multiplicity_adjustment: str(b.multiplicity_adjustment), p_values: str(b.p_values) },
			source: { path: str(s.path), sha256: str(s.sha256) }
		};
	}
	return { datasets, limitations: arr(root.limitations).map(str) };
}

export interface FlCurves {
	dataset: string; model_id: string; windows: number; matches: boolean; recomputed: { AUPRC: number; AUROC: number };
	frozen: { AUPRC: number; AUROC: number }; pr: [number, number][]; roc: [number, number][];
	confusion: { TP: number; FP: number; TN: number; FN: number }; threshold_rule: string; method: string; source: { path: string; sha256: string };
}
const points = (v: unknown): [number, number][] => arr(v).map((p) => { const a = arr(p); return [num(a[0]), num(a[1])]; });
export function parseFlCurves(value: unknown): FlCurves {
	const r = obj(value);
	if (r.classification !== 'DESCRIPTIVE_RECOMPUTATION_FROM_FROZEN_PREDICTIONS') bad();
	const c = obj(r.confusion_at_0_5); const re = obj(r.recomputed); const fr = obj(r.frozen); const s = obj(r.source);
	return { dataset: str(r.dataset), model_id: str(r.model_id), windows: num(r.windows), matches: r.recomputed_matches_frozen_point_metrics === true,
		recomputed: { AUPRC: num(re.AUPRC), AUROC: num(re.AUROC) }, frozen: { AUPRC: num(fr.AUPRC), AUROC: num(fr.AUROC) },
		pr: points(r.pr_curve), roc: points(r.roc_curve), confusion: { TP: num(c.TP), FP: num(c.FP), TN: num(c.TN), FN: num(c.FN) },
		threshold_rule: str(r.threshold_rule), method: str(r.method), source: { path: str(s.path), sha256: str(s.sha256) } };
}

export interface Architecture {
	architecture_id: string; parameter_count: number; input_shape: number[]; output_shape: number[]; channels: number; kernel_size: number;
	dilations: number[]; pooling: string; receptive_field_samples: number; layers: { name: string; type: string; parameters: number; output_shape: number[] }[]; notes: string[];
}
export function parseArchitecture(value: unknown): Architecture {
	const r = obj(value);
	if (r.classification !== 'DERIVED_FROM_ACTUAL_IMPLEMENTATION_ZERO_INPUT_SHAPE_TRACE') bad();
	return { architecture_id: str(r.architecture_id), parameter_count: num(r.parameter_count), input_shape: arr(r.input_shape).map(num), output_shape: arr(r.output_shape).map(num),
		channels: num(r.channels), kernel_size: num(r.kernel_size), dilations: arr(r.dilations).map(num), pooling: str(r.pooling), receptive_field_samples: num(r.receptive_field_samples),
		layers: arr(r.layers).map((l) => { const x = obj(l); return { name: str(x.name), type: str(x.type), parameters: num(x.parameters), output_shape: arr(x.output_shape).map(num) }; }),
		notes: arr(r.notes).map(str) };
}

export interface Bin { lower: number; upper: number; count: number; mean_probability: number; observed_positive_fraction: number }
export interface Calibration {
	label: string; constants: Record<string, unknown>; semantics: Record<string, string>; raw: Bin[]; scaled: Bin[]; reliability_method: string; not_applicable_to: string;
	source: { calibration_sha256: string; reliability_sha256: string };
}
// Empty bins carry null statistics in the frozen file; they are kept as null-free zeros with count 0 and are never plotted.
const bins = (v: unknown): Bin[] => arr(v).map((b) => { const x = obj(b); const count = num(x.count); return { lower: num(x.lower), upper: num(x.upper), count, mean_probability: count === 0 ? 0 : num(x.mean_probability), observed_positive_fraction: count === 0 ? 0 : num(x.observed_positive_fraction) }; });
export function parseCalibration(value: unknown): Calibration {
	const r = obj(value); const rel = obj(r.reliability); const s = obj(r.source); const sem = obj(r.probability_semantics);
	if (r.label !== 'MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY') bad();
	return { label: str(r.label), constants: obj(r.constants), semantics: { raw: str(sem.raw_probability), calibrated: str(sem.source_domain_calibrated_probability) },
		raw: bins(rel.raw), scaled: bins(rel.temperature_scaled), reliability_method: str(rel.method), not_applicable_to: str(r.not_applicable_to),
		source: { calibration_sha256: str(s.calibration_sha256), reliability_sha256: str(s.reliability_sha256) } };
}

export interface EvidenceEntry { id: string; title: string; statement?: string; decision?: string; why?: string; path: string; exists: boolean; sha256: string | null }
export interface Boundaries { boundaries: EvidenceEntry[]; chronology: EvidenceEntry[] }
const entry = (v: unknown): EvidenceEntry => { const x = obj(v);
	return { id: str(x.id), title: str(x.title), statement: x.statement === undefined ? undefined : str(x.statement), decision: x.decision === undefined ? undefined : str(x.decision),
		why: x.why === undefined ? undefined : str(x.why), path: str(x.path), exists: x.exists === true, sha256: nstr(x.sha256) }; };
export function parseBoundaries(value: unknown): Boundaries { const r = obj(value); return { boundaries: arr(r.boundaries).map(entry), chronology: arr(r.chronology).map(entry) }; }

export interface Reproducibility { git_commit: string | null; released_model: string; released_checkpoint_sha256: string; calibration_id: string; fields: [string, string][]; note: string }
export function parseReproducibility(value: unknown): Reproducibility {
	const r = obj(value); const rt = obj(r.runtime);
	const fields: [string, string][] = [['Observatory', str(r.observatory)], ['Predecessor UI', str(r.predecessor_ui)], ['Calibration SHA256', str(r.calibration_sha256)],
		['Preprocessing lock SHA256', str(r.preprocessing_lock_sha256)], ['Split manifest SHA256', str(r.split_manifest_sha256)], ['Window manifest SHA256', str(r.window_manifest_sha256)],
		['Protocol lock SHA256', str(r.protocol_lock_sha256)], ['FL-eval hash manifest SHA256', str(r.fl_eval_hash_manifest_sha256)], ['FL-eval frozen artifacts', String(num(r.fl_eval_artifact_count))],
		['Runtime (Python / torch)', `${str(rt.python)} / ${str(rt.torch)}`]];
	return { git_commit: nstr(r.git_commit), released_model: str(r.released_model), released_checkpoint_sha256: str(r.released_checkpoint_sha256), calibration_id: str(r.calibration_id), fields, note: str(r.note) };
}

export interface XaiIndex { method: Record<string, unknown>; cases: { case_type: string; record_id: string; window_start_s: number; window_end_s: number; F_x: number; F_baseline: number; output_difference: number; attribution_sum: number }[]; limitations: string[] }
export function parseXaiIndex(value: unknown): XaiIndex {
	const r = obj(value);
	if (r.classification !== 'FROZEN_RESEARCH_EVIDENCE') bad();
	return { method: obj(r.method), limitations: arr(r.limitations).map(str),
		cases: arr(r.cases).map((c) => { const x = obj(c); return { case_type: str(x.case_type), record_id: str(x.record_id), window_start_s: num(x.window_start_s), window_end_s: num(x.window_end_s), F_x: num(x.F_x), F_baseline: num(x.F_baseline), output_difference: num(x.output_difference), attribution_sum: num(x.attribution_sum) }; }) };
}
export interface XaiCase { case_type: string; record_id: string; model_input: [number, number, number, number][]; annotations: { time_s: number; symbol: string; aami_class: string; position: string }[]; overlay_normalization: string }
export function parseXaiCase(value: unknown): XaiCase {
	const r = obj(value);
	if (r.classification !== 'FROZEN_RESEARCH_EVIDENCE') bad();
	return { case_type: str(r.case_type), record_id: str(r.record_id), overlay_normalization: str(r.overlay_normalization),
		model_input: arr(r.model_input).map((p) => { const a = arr(p); return [num(a[0]), num(a[1]), num(a[2]), num(a[3])] as [number, number, number, number]; }),
		annotations: arr(r.annotations).map((a) => { const x = obj(a); return { time_s: num(x.time_s), symbol: str(x.symbol), aami_class: str(x.aami_class), position: str(x.position) }; }) };
}

export interface DatasetPreprocessing {
	datasets: { dataset: string; native_rate_hz: number; target_rate_hz: number; resampler_id: string; up: number; down: number; taps: number; group_delay_seconds: number; role: string | null; allowed_for_training: string | null; access_rule: string; coefficient_sha256: string;
		causality: { first_output_index_that_changed: number | null; altered_from_source_sample: number; output_samples: number; outputs_before_alteration_identical: boolean; synthetic_test_signal: string } }[];
	contract: Record<string, unknown>; label_contracts: { id: string; kind: string; rule: string }[]; raw_recordings: string; annotation_time_mapping: string;
}
export function parseDatasetPreprocessing(value: unknown): DatasetPreprocessing {
	const r = obj(value);
	if (r.classification !== 'FROZEN_METHOD_PLUS_DETERMINISTIC_DEMONSTRATION') bad();
	return { contract: obj(r.contract), raw_recordings: str(r.raw_recordings), annotation_time_mapping: str(r.annotation_time_mapping),
		label_contracts: arr(r.label_contracts).map((l) => { const x = obj(l); return { id: str(x.id), kind: str(x.kind), rule: str(x.rule) }; }),
		datasets: arr(r.datasets).map((d) => { const x = obj(d); const c = obj(x.causality);
			return { dataset: str(x.dataset), native_rate_hz: num(x.native_rate_hz), target_rate_hz: num(x.target_rate_hz), resampler_id: str(x.resampler_id), up: num(x.up), down: num(x.down), taps: num(x.taps), group_delay_seconds: num(x.group_delay_seconds),
				role: nstr(x.role), allowed_for_training: nstr(x.allowed_for_training), access_rule: str(x.access_rule), coefficient_sha256: str(x.coefficient_sha256),
				causality: { first_output_index_that_changed: c.first_output_index_that_changed === null ? null : num(c.first_output_index_that_changed), altered_from_source_sample: num(c.altered_from_source_sample), output_samples: num(c.output_samples), outputs_before_alteration_identical: c.outputs_before_alteration_identical === true, synthetic_test_signal: str(c.synthetic_test_signal) } }; }) };
}
