// Typed, fail-closed parser for the NHM_FINAL_SHOWCASE research bundle. Values are only validated and passed through; nothing is computed or hardcoded here.
type Rec = Record<string, unknown>;
const bad = (): never => { throw new Error('MALFORMED_SHOWCASE_BUNDLE'); };
const obj = (v: unknown): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : bad());
const str = (v: unknown): string => (typeof v === 'string' ? v : bad());
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : bad());
const nnum = (v: unknown): number | null => (v === null || v === undefined ? null : num(v));
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : bad());

export interface RoundPoint { round: number; training_weighted_mean_loss: number | null; validation_AUPRC: number; validation_AUROC: number; validation_BCE: number; selected_best_so_far: boolean }
export interface RoundLog { algorithm: string; condition: string; source: string; sha256: string; rounds: number; metric_scope: string; best_round_by_selection: number | null; series: RoundPoint[] }
export interface BundleModel { dataset: string; model_id: string; generation: string; algorithm: string; condition: string; mu: number | null; point: Record<string, number>; ci_95: Record<string, { lower: number; upper: number }> }
export interface ComparabilityRow { dataset: string; centralized_V2_AUPRC: number; federated_V2_FedAvg_IID_AUPRC: number; AUPRC_difference_federated_minus_centralized: number; centralized_V2_AUROC: number; federated_V2_FedAvg_IID_AUROC: number; AUROC_difference_federated_minus_centralized: number }
export interface Comparability { rows: ComparabilityRow[]; checks: { item: string; status: string; detail: string }[]; interpretations: { id: string; reading: string; support: string; limit: string }[]; verdict: string }
export interface SynthState { pooled: Record<string, number | null>; undefined: Record<string, string>; participant_macro_F1: number | null; uncertainty: Record<string, unknown>; per_participant: Record<string, Record<string, number | null>> }
export interface Synthetic { boundary_label: string; protocol_sha256: string; method_freeze_commit: string; candidate_digest: string; state_digests: Record<string, string>; holdout_windows: number; source: string; sha256: string; states: Record<string, SynthState> }
export interface LiveLinkParity { records_identical: boolean; window_count_identical: boolean; window_samples_and_timestamps_identical: boolean; dataset_identical_to_canonical: boolean; windows_monitored: number; dataset_sha256_live: string; dataset_sha256_canonical_site00: string; records_sha256_monitored: string }
export interface LiveLinkStatus {
	link_id: string; phase: string; link_label: string; run_id: string | null; status: string | null; candidate_ids: string[] | null; candidate_state_digest: string | null;
	candidate_digest_equals_canonical: boolean | null; parity: LiveLinkParity | null; blocked: { code: string; detail: string } | null; note: string | null; inference_http_statuses: Record<string, number> | null;
}
export interface ShowcaseBundle {
	lanes: Record<string, string>; datasets: Record<string, { claim_label: string; clusters: number; windows: number }>;
	models: BundleModel[]; round_logs: Record<string, RoundLog>; comparability: Comparability; limitations: string[];
	historical: Record<string, { AUPRC: number; AUROC: number }>; synthetic: Synthetic | null; live_link: LiveLinkStatus | null;
}
const sOrNull = (v: unknown): string | null => (v === null || v === undefined ? null : str(v));
export function parseLiveLink(value: unknown): LiveLinkStatus {
	const r = obj(value);
	let parity: LiveLinkParity | null = null;
	if (r.parity) {
		const p = obj(r.parity); const b = (v: unknown): boolean => (typeof v === 'boolean' ? v : bad());
		parity = { records_identical: b(p.records_identical), window_count_identical: b(p.window_count_identical), window_samples_and_timestamps_identical: b(p.window_samples_and_timestamps_identical),
			dataset_identical_to_canonical: b(p.dataset_identical_to_canonical), windows_monitored: num(p.windows_monitored), dataset_sha256_live: str(p.dataset_sha256_live),
			dataset_sha256_canonical_site00: str(p.dataset_sha256_canonical_site00), records_sha256_monitored: str(p.records_sha256_monitored) };
	}
	const mon = r.monitoring ? obj(r.monitoring) : null;
	const statuses = mon && mon.inference_http_statuses ? Object.fromEntries(Object.entries(obj(mon.inference_http_statuses)).map(([k, v]) => [k, num(v)])) : null;
	const blocked = r.blocked ? { code: str(obj(r.blocked).code), detail: String(obj(r.blocked).detail ?? '') } : null;
	return { link_id: typeof r.link_id === 'string' ? r.link_id : 'RECORDED', phase: str(r.phase), link_label: str(r.link_label), run_id: sOrNull(r.run_id), status: sOrNull(r.status),
		candidate_ids: Array.isArray(r.candidate_ids) ? r.candidate_ids.map(str) : null, candidate_state_digest: sOrNull(r.candidate_state_digest),
		candidate_digest_equals_canonical: typeof r.candidate_digest_equals_canonical === 'boolean' ? r.candidate_digest_equals_canonical : null, parity, blocked, note: sOrNull(r.note), inference_http_statuses: statuses };
}
const nrec = (v: unknown): Record<string, number | null> => Object.fromEntries(Object.entries(obj(v)).map(([k, x]) => [k, nnum(x)]));

export function parseShowcase(value: unknown): ShowcaseBundle {
	const root = obj(value);
	if (root.schema_version !== 'NHM_FINAL_SHOWCASE_RESEARCH_BUNDLE_V1') bad();
	const round_logs: Record<string, RoundLog> = {};
	for (const [k, raw] of Object.entries(obj(root.round_logs))) {
		const l = obj(raw);
		round_logs[k] = { algorithm: str(l.algorithm), condition: str(l.condition), source: str(l.source), sha256: str(l.sha256), rounds: num(l.rounds), metric_scope: str(l.metric_scope),
			best_round_by_selection: nnum(l.best_round_by_selection),
			series: arr(l.series).map((p) => { const s = obj(p); return { round: num(s.round), training_weighted_mean_loss: nnum(s.training_weighted_mean_loss), validation_AUPRC: num(s.validation_AUPRC), validation_AUROC: num(s.validation_AUROC), validation_BCE: num(s.validation_BCE), selected_best_so_far: s.selected_best_so_far === true }; }) };
	}
	const c = obj(root.comparability);
	const historical: ShowcaseBundle['historical'] = {};
	for (const [k, v] of Object.entries(obj(root.historical_centralized))) { if (k.startsWith('MODEL_')) { const e = obj(v); historical[k] = { AUPRC: num(e.AUPRC), AUROC: num(e.AUROC) }; } }
	let synthetic: Synthetic | null = null;
	if (root.synthetic) {
		const s = obj(root.synthetic); const states: Record<string, SynthState> = {};
		for (const [k, raw] of Object.entries(obj(s.states))) {
			const e = obj(raw);
			states[k] = { pooled: nrec(e.pooled), undefined: Object.fromEntries(Object.entries(obj(e.undefined)).map(([a, b]) => [a, str(b)])), participant_macro_F1: nnum(e.participant_macro_F1), uncertainty: obj(e.uncertainty),
				per_participant: Object.fromEntries(Object.entries(obj(e.per_participant)).map(([a, b]) => [a, nrec(b)])) };
		}
		synthetic = { boundary_label: str(s.boundary_label), protocol_sha256: str(s.protocol_sha256), method_freeze_commit: str(s.method_freeze_commit), candidate_digest: str(s.candidate_digest),
			state_digests: Object.fromEntries(Object.entries(obj(s.state_digests)).map(([a, b]) => [a, str(b)])), holdout_windows: num(s.holdout_windows), source: str(s.source), sha256: str(s.sha256), states };
	}
	return {
		lanes: Object.fromEntries(Object.entries(obj(root.lanes)).map(([a, b]) => [a, str(b)])),
		datasets: Object.fromEntries(Object.entries(obj(root.datasets)).map(([a, b]) => { const d = obj(b); return [a, { claim_label: str(d.claim_label), clusters: num(d.clusters), windows: num(d.windows) }]; })),
		models: arr(root.models).map((raw) => { const m = obj(raw); const ci: BundleModel['ci_95'] = {}; for (const [k, v] of Object.entries(obj(m.ci_95))) { const i = obj(v); ci[k] = { lower: num(i.lower), upper: num(i.upper) }; }
			return { dataset: str(m.dataset), model_id: str(m.model_id), generation: str(m.generation), algorithm: str(m.algorithm), condition: str(m.condition), mu: nnum(m.mu), point: Object.fromEntries(Object.entries(obj(m.point)).map(([k, v]) => [k, num(v)])), ci_95: ci }; }),
		round_logs,
		comparability: { rows: arr(c.rows).map((raw) => { const r = obj(raw); return { dataset: str(r.dataset), centralized_V2_AUPRC: num(r.centralized_V2_AUPRC), federated_V2_FedAvg_IID_AUPRC: num(r.federated_V2_FedAvg_IID_AUPRC),
				AUPRC_difference_federated_minus_centralized: num(r.AUPRC_difference_federated_minus_centralized), centralized_V2_AUROC: num(r.centralized_V2_AUROC), federated_V2_FedAvg_IID_AUROC: num(r.federated_V2_FedAvg_IID_AUROC),
				AUROC_difference_federated_minus_centralized: num(r.AUROC_difference_federated_minus_centralized) }; }),
			checks: arr(c.checks).map((raw) => { const r = obj(raw); return { item: str(r.item), status: str(r.status), detail: str(r.detail) }; }),
			interpretations: arr(c.interpretations).map((raw) => { const r = obj(raw); return { id: str(r.id), reading: str(r.reading), support: str(r.support), limit: str(r.limit) }; }), verdict: str(c.verdict) },
		limitations: arr(root.limitations).map(str), historical, synthetic, live_link: root.live_link ? parseLiveLink(root.live_link) : null
	};
}
