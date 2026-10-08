import { describe, expect, it } from 'vitest';
import { cell, parseFl10, parseFl10Job, tableToCsv } from '../fl10';

function fixture(overrides: { status?: string; rounds?: number } = {}) {
	const specs: Record<string, unknown> = {};
	for (let i = 1; i <= 20; i++) {
		const id = `FL10_FIG${String(i).padStart(2, '0')}`;
		specs[id] = { id, title: id, caption: 'c', sources: ['s'], group: 'g', synthetic_label: 'L', note: null, views: [{ id: 'v', label: 'V', kind: 'lines', series: [{ name: 'a', x: [0, 1], y: [null, 1] }] }] };
	}
	const tables: Record<string, unknown> = {};
	for (let i = 1; i <= 12; i++) {
		const id = `FL10_TAB${String(i).padStart(2, '0')}`;
		tables[id] = { id, title: id, columns: ['a', 'b'], rows: [['x', null], ['y', 2]], caption: 'c', sources: [], synthetic_label: 'L' };
	}
	return { overview: { source_label: 'S', run_id: 'R', synthetic_label: 'L', run: { status: overrides.status ?? 'COMPLETED', rounds_committed: overrides.rounds ?? 10 } }, specs, tables };
}

describe('FL10 payload parser', () => {
	it('accepts a complete ten-round payload and keeps undefined values as null', () => {
		const p = parseFl10(fixture());
		expect(Object.keys(p.specs)).toHaveLength(20);
		expect(Object.keys(p.tables)).toHaveLength(12);
		expect(p.specs.FL10_FIG01.views[0].series[0].y[0]).toBeNull();
		expect(cell(null)).toBe('UNDEFINED');
	});
	it('never presents a partial or failed run as a ten-round result', () => {
		expect(() => parseFl10(fixture({ rounds: 7 }))).toThrow('MALFORMED_FL10_BUNDLE');
		expect(() => parseFl10(fixture({ status: 'INCOMPLETE_NOT_A_CANDIDATE' }))).toThrow('MALFORMED_FL10_BUNDLE');
	});
	it('fails closed on a missing figure, unknown chart kind, non-finite value or ragged table', () => {
		const missing = fixture(); delete (missing.specs as Record<string, unknown>).FL10_FIG07;
		expect(() => parseFl10(missing)).toThrow('MALFORMED_FL10_BUNDLE');
		const kind = fixture(); ((kind.specs.FL10_FIG02 as { views: { kind: string }[] }).views[0]).kind = 'decorative';
		expect(() => parseFl10(kind)).toThrow('MALFORMED_FL10_BUNDLE');
		const nan = fixture(); ((nan.specs.FL10_FIG03 as { views: { series: { y: unknown[] }[] }[] }).views[0].series[0].y[1]) = Number.NaN;
		expect(() => parseFl10(nan)).toThrow('MALFORMED_FL10_BUNDLE');
		const ragged = fixture(); ((ragged.tables.FL10_TAB01 as { rows: unknown[][] }).rows[0]) = ['only-one'];
		expect(() => parseFl10(ragged)).toThrow('MALFORMED_FL10_BUNDLE');
	});
	it('exports CSV with blanks (not zeros) for undefined values and parses job status', () => {
		const t = parseFl10(fixture()).tables.FL10_TAB01;
		expect(tableToCsv(t)).toBe('a,b\nx,\ny,2\n');
		const job = parseFl10Job({ job_id: 'J', mode: 'A', phase: 'TRAINING', source_label: 'LIVE RUN (this session)', candidate_promoted: false, note: 'n', rounds_committed: 3 });
		expect(job.phase).toBe('TRAINING');
		expect(job.candidate_promoted).toBe(false);
	});
});
