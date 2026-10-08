// Typed, fail-closed parser for the NHM-FL10 payload (overview + chart specs + tables). Values are validated and passed through; nothing is computed or hardcoded here.
type Rec = Record<string, unknown>;
const bad = (): never => { throw new Error('MALFORMED_FL10_BUNDLE'); };
const obj = (v: unknown): Rec => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Rec) : bad());
const str = (v: unknown): string => (typeof v === 'string' ? v : bad());
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : bad());
const finiteOrNull = (v: unknown): boolean => v === null || (typeof v === 'number' && Number.isFinite(v));

export const FL10_KINDS = ['lines', 'curves', 'bars', 'stacked', 'heatmap', 'hist', 'confusion', 'intervals', 'diagram', 'lineage'] as const;
export type Fl10Kind = (typeof FL10_KINDS)[number];
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface Fl10View { id: string; label: string; kind: Fl10Kind; [key: string]: any }
export interface Fl10Spec { id: string; title: string; caption: string; sources: string[]; group: string; synthetic_label: string; note: string | null; views: Fl10View[] }
export interface Fl10Table { id: string; title: string; columns: string[]; rows: unknown[][]; caption: string; sources: string[]; synthetic_label: string }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Overview = Record<string, any>;
export interface Fl10Payload { overview: Overview; specs: Record<string, Fl10Spec>; tables: Record<string, Fl10Table> }
export interface Fl10Recorded { key: string; label: string; mode: string; run_id: string; candidate_sha256: string; status: string }
export interface Fl10Job { job_id: string; mode: string; phase: string; source_label: string; candidate_promoted: boolean; note: string; rounds_committed?: number; events?: { event: string; round?: number; client_id?: string; t: number }[]; failure?: { type: string; message: string } }

const SPEC_IDS = Array.from({ length: 20 }, (_, i) => `FL10_FIG${String(i + 1).padStart(2, '0')}`);
const TABLE_IDS = Array.from({ length: 12 }, (_, i) => `FL10_TAB${String(i + 1).padStart(2, '0')}`);

export function parseFl10(value: unknown): Fl10Payload {
	const root = obj(value);
	const overview = obj(root.overview);
	const run = obj(overview.run);
	if (run.status !== 'COMPLETED' || run.rounds_committed !== 10) bad();            // a partial run is never presented as a ten-round result
	str(overview.synthetic_label); str(overview.source_label); str(overview.run_id);
	const specs: Record<string, Fl10Spec> = {};
	const rawSpecs = obj(root.specs);
	for (const id of SPEC_IDS) {
		const s = obj(rawSpecs[id]);
		const views = arr(s.views).map((raw) => { const v = obj(raw); if (!FL10_KINDS.includes(v.kind as Fl10Kind)) bad(); return { ...v, id: str(v.id), label: str(v.label), kind: v.kind as Fl10Kind } as Fl10View; });
		if (views.length === 0) bad();
		for (const v of views) for (const series of (Array.isArray(v.series) ? v.series : []) as Rec[]) for (const key of ['y', 'values'] as const) if (key in series) for (const n of arr(series[key])) if (!finiteOrNull(n)) bad();
		specs[id] = { id, title: str(s.title), caption: str(s.caption), sources: arr(s.sources).map(str), group: str(s.group), synthetic_label: str(s.synthetic_label), note: typeof s.note === 'string' ? s.note : null, views };
	}
	const tables: Record<string, Fl10Table> = {};
	const rawTables = obj(root.tables);
	for (const id of TABLE_IDS) {
		const t = obj(rawTables[id]);
		const columns = arr(t.columns).map(str);
		const rows = arr(t.rows).map((r) => { const row = arr(r); if (row.length !== columns.length) bad(); return row; });
		tables[id] = { id, title: str(t.title), columns, rows, caption: str(t.caption), sources: arr(t.sources).map(str), synthetic_label: str(t.synthetic_label) };
	}
	return { overview, specs, tables };
}

export function parseFl10Recorded(value: unknown): Fl10Recorded[] {
	return arr(value).map((raw) => { const r = obj(raw); return { key: str(r.key), label: str(r.label), mode: str(r.mode), run_id: str(r.run_id), candidate_sha256: str(r.candidate_sha256), status: str(r.status) }; });
}

export function parseFl10Job(value: unknown): Fl10Job {
	const r = obj(value);
	return { job_id: str(r.job_id), mode: str(r.mode), phase: str(r.phase), source_label: str(r.source_label), candidate_promoted: r.candidate_promoted === true, note: str(r.note),
		rounds_committed: typeof r.rounds_committed === 'number' ? r.rounds_committed : undefined, events: Array.isArray(r.events) ? (r.events as Fl10Job['events']) : [],
		failure: r.failure ? { type: str(obj(r.failure).type), message: str(obj(r.failure).message) } : undefined };
}

export const cell = (v: unknown, d = 6): string => (v === null || v === undefined ? 'UNDEFINED' : typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(d)) : typeof v === 'boolean' ? String(v) : String(v));

export function tableToCsv(t: Fl10Table): string {
	const esc = (v: unknown) => { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
	return [t.columns.map(esc).join(','), ...t.rows.map((r) => r.map(esc).join(','))].join('\n') + '\n';
}

export function tableToMarkdown(t: Fl10Table): string {
	const escape = (value: unknown) => (value === null || value === undefined ? 'UNDEFINED'
		: String(value).replaceAll('|', '\\|').replaceAll('\n', ' '));
	return `# ${t.title}\n\n${t.caption}\n\n`
		+ `| ${t.columns.map(escape).join(' | ')} |\n`
		+ `| ${t.columns.map(() => '---').join(' | ')} |\n`
		+ t.rows.map((row) => `| ${row.map(escape).join(' | ')} |`).join('\n')
		+ `\n\n${t.synthetic_label}\n`;
}

export async function sha256Hex(text: string): Promise<string> {
	const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
	return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
