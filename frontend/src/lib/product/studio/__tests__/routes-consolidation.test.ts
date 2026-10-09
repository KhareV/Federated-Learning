// Static guards over the consolidation: nothing valuable lost, retired route redirects, protected pages untouched, and every FL10 figure/table has a home in the Studio.
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = path.resolve(__dirname, '../../../..');
const read = (p: string) => readFileSync(path.join(SRC, p), 'utf-8');
function walk(dir: string, out: string[] = []): string[] {
	for (const name of readdirSync(dir)) {
		if (name === '__tests__' || name === 'node_modules' || name.startsWith('.')) continue;
		const full = path.join(dir, name);
		if (statSync(full).isDirectory()) walk(full, out);
		else if (/\.(svelte|ts)$/.test(name)) out.push(full);
	}
	return out;
}

const RETAINED = ['federation', 'federation/live', 'federation/rounds', 'federation/clients', 'federation/privacy', 'observatory', 'observatory/evidence', 'observatory/federation', 'observatory/federation/[client_id]', 'observatory/federation-replay',
	'observatory/fl10', 'observatory/model', 'observatory/outcomes', 'observatory/provenance', 'observatory/replay', 'observatory/research', 'observatory/scenarios', 'observatory/storyboard', 'observatory/tour'];

describe('route inventory after consolidation', () => {
	it('every route that existed before consolidation still exists (no deep link or bookmark is lost)', () => {
		for (const r of RETAINED) expect(existsSync(path.join(SRC, `routes/app/${r}/+page.svelte`)), r).toBe(true);
	});
	it('the retired FL10 Observatory page is a pure redirect into the Federation Studio that preserves ?run=', () => {
		const page = read('routes/app/observatory/fl10/+page.svelte');
		expect(page).toContain("goto(`/app/federation/live?run=${encodeURIComponent(");
		expect(page).toContain("page.url.searchParams.get('run')");
		expect(page).not.toMatch(/Fl10Chart|Fl10Table|fl10Start|fl10Recorded/);
		expect(page).toContain('moved into the Federation Studio');
	});
	it('no navigation or page links to the retired page any more, and the Observatory home points at the Studio', () => {
		const offenders = walk(SRC).filter((f) => !f.endsWith(path.join('observatory', 'fl10', '+page.svelte'))).filter((f) => /href=["']\/app\/observatory\/fl10/.test(readFileSync(f, 'utf-8')));
		expect(offenders).toEqual([]);
		expect(read('routes/app/observatory/+page.svelte')).toMatch(/href="\/app\/federation">Federation Studio/);
	});
	it('the frozen scientific outcomes page is protected: still the frozen-evidence page with its showcase source', () => {
		const page = read('routes/app/observatory/outcomes/+page.svelte');
		expect(page).toContain('FROZEN RESEARCH EVIDENCE · SCIENTIFIC LANE B');
		expect(page).toContain('observatoryShowcase');
		expect(page).toContain('data-testid="comparability-matrix"');
	});
	it('the storyboard keeps its guided steps and live-link control and now points to the Studio', () => {
		const page = read('routes/app/observatory/storyboard/+page.svelte');
		expect(page).toContain('data-testid="storyboard-step"');
		expect(page).toContain('observatoryLiveLinkStart');
		expect(page).toContain('/app/federation');
	});
});

describe('every migrated FL10 capability has a home in the Studio', () => {
	const tabs = read('lib/components/product/studio/AnalysisTabs.svelte');
	it('all 20 figures and all 12 tables are assigned to at least one analysis tab', () => {
		for (let i = 1; i <= 20; i++) expect(tabs, `FIG${i}`).toContain(`FL10_FIG${String(i).padStart(2, '0')}`);
		for (let i = 1; i <= 12; i++) expect(tabs, `TAB${i}`).toContain(`FL10_TAB${String(i).padStart(2, '0')}`);
	});
	it('overview facts, round comparison, client history, research bridge, exports and manifest download are wired in', () => {
		for (const c of ['RunOverview', 'RoundComparison', 'ClientHistory', 'ResearchBridge', 'ExportPanel', 'RoundClientPanel']) {
			expect(existsSync(path.join(SRC, `lib/components/product/studio/${c}.svelte`)), c).toBe(true);
			expect(tabs).toContain(c);
		}
		expect(read('lib/components/product/studio/ExportPanel.svelte')).toContain('Download verification manifest');
		expect(read('lib/components/product/studio/ResearchBridge.svelte')).toContain('/app/observatory/outcomes');
	});
	it('the live start of both source modes is offered by the Studio and reaches the 10-round engine', () => {
		const starter = read('lib/components/product/studio/StudioRunStarter.svelte');
		expect(starter).toContain('LIVE_MONITORED_SITE_00');
		expect(starter).toContain('CANONICAL_SYNTHETIC');
		expect(read('lib/product/api.ts')).toContain("'/studio/runs', { run_length: choice.run_length");
	});
	it('the original Federation Studio components are still the ones rendering the network and timeline', () => {
		const live = read('routes/app/federation/live/+page.svelte');
		for (const c of ['ClientGrid', 'ProcessStepper', 'RoundProgress', 'ModelStateTransition', 'CandidateLifecycle', 'FederationTimeline', 'ClientDetailPanel', 'TechnicalEvidence']) expect(live, c).toContain(`${c}.svelte`);
		expect(live).toContain('ownerBoundClientId(product.authState.system?.auth_provider');       // the owner-binding rule is unchanged
	});
});
