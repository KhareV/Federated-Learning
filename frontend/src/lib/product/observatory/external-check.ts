// Typed, fail-closed parser for the Observatory's external-check evidence on real ECG that was never part of any model's training, selection or evaluation (a record-level extension, outside the locked scope).
// No value is computed here: everything shown is read from the hash-verified stored report.
type Rec = Record<string, unknown>;
const bad = (): never => { throw new Error('MALFORMED_EXTERNAL_CHECK_EVIDENCE'); };
const obj = (v: unknown): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : bad());
const str = (v: unknown): string => (typeof v === 'string' ? v : bad());
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : bad());
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : bad());
const pair = (v: unknown): [number, number] => { const a = arr(v); return a.length === 2 ? [num(a[0]), num(a[1])] : bad(); };

export interface PairedDelta { delta: number; ci95: [number, number]; share_better: number }
export interface ExternalRow {
	model: string; AUROC: number; AUROC_ci: [number, number]; AUPRC: number; AUPRC_ci: [number, number]; lift: number; F1: number; F1_ci: [number, number];
	sensitivity: number; specificity: number; precision: number; paired_vs_central_V2: { AUROC: PairedDelta; AUPRC: PairedDelta } | null;
}
export interface ExternalSet { name: string; records: number; positives: number; patients: number; prevalence: number; bootstrap_replicates: number; rows: ExternalRow[] }
export interface RuleBlock { rule: string; title: string; records: number; positives: number; rows: { model: string; AUROC: number; AUPRC: number; lift: number }[] }
export interface ExternalCheck {
	label: string; claim_boundary: string; target: string; records_scored: number; exclusions: Record<string, number>; threshold: number; calibration: string;
	report: { path: string; sha256: string }; protocol: { path: string; sha256: string; verified: true };
	models: string[]; sets: ExternalSet[]; label_rules: RuleBlock[]; error_analysis: { group: string; records: number; share_flagged: number }[];
	label_agreement: { both: number; statement_only: number; extra_beats_only: number }; limitations: string[];
}

function delta(v: unknown): PairedDelta { const o = obj(v); return { delta: num(o.delta), ci95: pair(o.ci95), share_better: num(o.share_better) }; }

export function parseExternalCheck(value: unknown): ExternalCheck {
	const r = obj(value);
	if (r.classification !== 'FROZEN_EXTENSION_EVIDENCE') bad();
	const protocol = obj(r.protocol);
	if (protocol.verified !== true) bad();                                   // an unverified protocol is never displayed
	const exclusions: Record<string, number> = {};
	for (const [k, v] of Object.entries(obj(r.exclusions))) exclusions[k] = num(v);
	const agreement = obj(r.label_agreement);
	return {
		label: str(r.label), claim_boundary: str(r.claim_boundary), target: str(r.target), records_scored: num(r.records_scored), exclusions, threshold: num(r.threshold), calibration: str(r.calibration),
		report: { path: str(obj(r.report).path), sha256: str(obj(r.report).sha256) }, protocol: { path: str(protocol.path), sha256: str(protocol.sha256), verified: true },
		models: arr(r.models).map(str),
		sets: arr(r.sets).map((s) => { const o = obj(s); return {
			name: str(o.name), records: num(o.records), positives: num(o.positives), patients: num(o.patients), prevalence: num(o.prevalence), bootstrap_replicates: num(o.bootstrap_replicates),
			rows: arr(o.rows).map((x) => { const q = obj(x); const p = q.paired_vs_central_V2; return {
				model: str(q.model), AUROC: num(q.AUROC), AUROC_ci: pair(q.AUROC_ci), AUPRC: num(q.AUPRC), AUPRC_ci: pair(q.AUPRC_ci), lift: num(q.lift), F1: num(q.F1), F1_ci: pair(q.F1_ci),
				sensitivity: num(q.sensitivity), specificity: num(q.specificity), precision: num(q.precision), paired_vs_central_V2: p === null ? null : { AUROC: delta(obj(p).AUROC), AUPRC: delta(obj(p).AUPRC) } }; }) }; }),
		label_rules: arr(r.label_rules).map((b) => { const o = obj(b); return { rule: str(o.rule), title: str(o.title), records: num(o.records), positives: num(o.positives),
			rows: arr(o.rows).map((x) => { const q = obj(x); return { model: str(q.model), AUROC: num(q.AUROC), AUPRC: num(q.AUPRC), lift: num(q.lift) }; }) }; }),
		error_analysis: arr(r.error_analysis).map((g) => { const o = obj(g); return { group: str(o.group), records: num(o.records), share_flagged: num(o.share_flagged) }; }),
		label_agreement: { both: num(agreement.both), statement_only: num(agreement.statement_only), extra_beats_only: num(agreement.extra_beats_only) }, limitations: arr(r.limitations).map(str)
	};
}
