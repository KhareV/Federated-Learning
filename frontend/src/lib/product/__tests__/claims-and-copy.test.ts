// Static guards over the PRODUCT source (CAPG4): secrets, remote assets, direct inference calls,
// locally synthesised monitoring states, claim wording, fake metrics, landing CTAs.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = path.resolve(__dirname, '../../../');
function walk(dir: string, out: string[] = []): string[] {
	for (const name of readdirSync(dir)) {
		if (name === '__tests__' || name === 'node_modules' || name.startsWith('.')) continue;
		const full = path.join(dir, name);
		if (statSync(full).isDirectory()) walk(full, out);
		else if (/\.(svelte|ts|css|html)$/.test(name)) out.push(full);
	}
	return out;
}
const rel = (f: string) => path.relative(SRC, f);
const read = (p: string) => readFileSync(path.join(SRC, p), 'utf-8');
const ALL = walk(SRC);
const PRODUCT = ALL.filter((f) => /^(lib\/product|lib\/components\/product|routes\/app|routes\/sign-in)/.test(rel(f)));
const stripComments = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/<!--[\s\S]*?-->/g, '');

describe('product source layout', () => {
	it('exists: the product shell routes and the typed product layer', () => {
		expect(PRODUCT.length).toBeGreaterThan(20);
		for (const p of ['routes/sign-in/+page.svelte', 'routes/app/+page.svelte', 'routes/app/device/+page.svelte', 'routes/app/monitoring/+page.svelte', 'lib/product/api.ts', 'lib/product/types.ts', 'lib/product/state.svelte.ts', 'lib/product/auth.ts']) {
			expect(() => read(p)).not.toThrow();
		}
	});
	it('every product destination exists; CAP-009 research routes use the real evidence API', () => {
		for (const p of ['federation', 'federation/clients', 'federation/rounds', 'federation/live', 'federation/privacy', 'models', 'research/ml', 'research/fl', 'system', 'about', 'history']) {
			expect(() => read(`routes/app/${p}/+page.svelte`)).not.toThrow();
		}
	for (const [route, method] of [['research/ml', 'researchMl'], ['research/fl', 'researchFl']]) {
		const page = read(`routes/app/${route}/+page.svelte`);
		expect(page).not.toContain('FuturePhase');
		expect(page).toContain(`product.api.${method}()`);
	}
		for (const p of ['federation', 'federation/clients', 'federation/rounds', 'federation/live', 'federation/privacy', 'models']) {
			expect(read(`routes/app/${p}/+page.svelte`)).not.toContain('FuturePhase'); // CAP-008: real CAP-007-backed pages
		}
	});
});

describe('secrets and dependencies', () => {
	it('the frontend source contains no Clerk secret/JWT key or session-token fixture', () => {
		const forbidden = [/CLERK_SECRET_KEY/, /CLERK_JWT_KEY/, /sk_(live|test)_[A-Za-z0-9]{8,}/, /-----BEGIN [A-Z ]*PRIVATE KEY-----/, /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./];
		for (const file of ALL) {
			const text = readFileSync(file, 'utf-8');
			for (const pattern of forbidden) expect(pattern.test(text), `${rel(file)} matches ${pattern}`).toBe(false);
		}
	});
	it('only the public publishable key name is read; the deprecated clerk-sveltekit adapter is not used', () => {
		const text = PRODUCT.map((f) => readFileSync(f, 'utf-8')).join('\n');
		expect(text).toContain('VITE_CLERK_PUBLISHABLE_KEY');
		expect(text).not.toMatch(/clerk-sveltekit/);
		const pkg = JSON.parse(readFileSync(path.resolve(SRC, '../package.json'), 'utf-8'));
		const deps = { ...pkg.dependencies, ...pkg.devDependencies };
		expect(Object.keys(deps).some((k) => /clerk/i.test(k))).toBe(false); // pin lives in the additive clerk-sdk package
		const sdk = JSON.parse(readFileSync(path.resolve(SRC, '../clerk-sdk/package.json'), 'utf-8'));
		expect(sdk.dependencies).toEqual({ '@clerk/clerk-js': '6.37.0' }); // exact pin, no range
	});
	it('Clerk is only imported lazily (dynamic import) from the auth module', () => {
		for (const file of PRODUCT) {
			const text = stripComments(readFileSync(file, 'utf-8'));
			expect(/^\s*import\s+[^(]*from\s+['"]@clerk\//m.test(text), rel(file)).toBe(false);
		}
		expect(stripComments(read('lib/product/auth.ts'))).toMatch(/await import\('@clerk\/clerk-js'\)/);
	});
	it('no new frontend dependency category was added (no state/router/chart/websocket library)', () => {
		const pkg = JSON.parse(readFileSync(path.resolve(SRC, '../package.json'), 'utf-8'));
		const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
		for (const banned of ['redux', 'zustand', 'react', 'vue', 'next', 'socket.io', 'socket.io-client', 'chart.js', 'd3', 'echarts', 'axios', 'react-router']) {
			expect(names).not.toContain(banned);
		}
	});
});

describe('product monitoring path purity', () => {
	const live = PRODUCT.filter((f) => !f.endsWith('.d.ts'));
	it('the product never calls the research inference route directly', () => {
		for (const file of live) {
			const text = stripComments(readFileSync(file, 'utf-8'));
			expect(/infer-window/.test(text), rel(file)).toBe(false);
			expect(/from ['"]\$lib\/api\/nhm-v1['"]/.test(text), rel(file)).toBe(false);
			expect(/\$lib\/services\/(api|websocket)/.test(text), rel(file)).toBe(false);
		}
	});
	it('the product does not import the legacy dashboard session logic that maps 422 -> RECHECK_SENSOR', () => {
		for (const file of live) {
			const text = stripComments(readFileSync(file, 'utf-8'));
			expect(/dashboard\/session|httpErrorPresentation|createDashboardSession/.test(text), rel(file)).toBe(false);
		}
	});
	it('no monitoring state is assigned anywhere in product code except from a monitoring.state event', () => {
		const model = stripComments(read('lib/product/live-model.ts'));
		const assignments = [...model.matchAll(/this\.monitoringState\s*=\s*([^;]+);/g)].map((m) => m[1].trim());
		expect(assignments.filter((a) => a !== 'null' && a !== 'event.payload.monitoring_state')).toEqual([]);
		for (const file of live) {
			const text = stripComments(readFileSync(file, 'utf-8'));
			if (rel(file).endsWith('types.ts') || rel(file).endsWith('events.ts')) continue; // vocabularies / validators
			if (rel(file).includes('routes/app') || rel(file).includes('components/product')) {
				expect(/['"]RECHECK_SENSOR['"]/.test(text), `${rel(file)} mentions RECHECK_SENSOR as a literal state`).toBe(false);
			}
		}
	});
	it('the product does not implement threshold / quality / HR / SpO2 / debounce logic', () => {
		const ids = (t: string) => stripComments(t).replace(/(['"`])(?:(?!\1)[^\\\n]|\\.)*\1/g, '""');
		for (const file of live.filter((f) => f.endsWith('.ts'))) {
			const code = ids(readFileSync(file, 'utf-8'));
			expect(/\b(debounce|sigmoid|softmax|calibrat\w+\s*\(|computeHr|computeSpo2|classifyQuality)\b/i.test(code), rel(file)).toBe(false);
			expect(/(probability|threshold)\s*[<>]=?\s*/i.test(code), `${rel(file)} compares a probability/threshold`).toBe(false);
		}
	});
	it('no model / checkpoint / calibration selector exists in product request code', () => {
		const api = stripComments(read('lib/product/api.ts'));
		expect(/model_id|checkpoint|threshold|calibration_id/.test(api)).toBe(false);
	});
	it('the WebSocket URL builder and store never place a token in the URL', () => {
		const text = stripComments(read('lib/product/api.ts') + read('lib/product/socket.ts') + read('lib/product/state.svelte.ts'));
		expect(/new WebSocket\([^)]*(token|Bearer|\?)/.test(text)).toBe(false);
		expect(/localStorage|sessionStorage|indexedDB/.test(text + stripComments(read('lib/product/auth.ts')))).toBe(false);
	});
});

describe('offline product path', () => {
	it('/sign-in and /app/* sources, app.html and app.css reference no remote host', () => {
		const targets = [...PRODUCT.filter((f) => /routes\/(app|sign-in)|components\/product/.test(rel(f))), path.join(SRC, 'app.html'), path.join(SRC, 'app.css'), path.join(SRC, 'routes/+layout.svelte')];
		for (const file of targets) {
			const text = stripComments(readFileSync(file, 'utf-8')).replace(/xmlns="http:\/\/www\.w3\.org\/\d+\/svg"/g, '');
			expect(/https?:\/\/(?!localhost|127\.0\.0\.1)/.test(text), rel(file)).toBe(false);
			expect(/googleapis|gstatic|unsplash|clerk\.com|cdn\./i.test(text), rel(file)).toBe(false);
		}
	});
	it('the landing page also needs no remote asset (fonts, images)', () => {
		const text = stripComments(read('routes/+page.svelte'));
		const noInline = text.replace(/url\(["']?data:[^)]*\)/g, '').replace(/xmlns=["']http:\/\/www\.w3\.org\/\d+\/svg["']/g, '');
		expect(/https?:\/\//.test(noInline)).toBe(false);
	});
});

describe('landing page product story and claim corrections', () => {
	const landing = read('routes/+page.svelte');
	it('primary CTAs go to the product flow, not the legacy /monitor', () => {
		expect(landing).not.toMatch(/href="\/monitor"/);
		expect((landing.match(/href="\/sign-in"/g) ?? []).length).toBeGreaterThanOrEqual(4);
		expect(landing).toContain('OPEN NHM');
	});
	it('frames NHM as a federated physiological monitoring research platform with the three pillars', () => {
		expect(landing).toContain('Federated physiological');
		expect(landing).toContain('monitoring research platform');
		for (const pillar of ['LIVE MONITORING', 'FEDERATED MODEL DEVELOPMENT', 'HARDWARE-READY SOURCE ARCHITECTURE']) expect(landing).toContain(pillar);
		expect(landing).toMatch(/not a diagnostic or medical device/i);
	});
	it('no longer claims attached hardware, edge inference, or real participating cities', () => {
		for (const bad of [/ECG STREAM \/ CONNECTED/, /PPG STREAM \/ CONNECTED/, /SENSOR ARRAY \/ READY/, /titanium/i, /dual-core edge machine learning/i, /<strong>ESP32<\/strong>/, /PROCESS LOCALLY/, /Delhi|Mumbai|Chennai|London|New York|Tokyo|Singapore/, /lat:\s*\d/, /DottedMap/]) {
			expect(bad.test(landing), String(bad)).toBe(false);
		}
		expect(landing).toContain('PHYSICAL HARDWARE / NOT CONNECTED');
		expect(landing).toContain('ILLUSTRATIVE NETWORK TOPOLOGY - NOT PARTICIPATING INSTITUTIONS');
		expect(landing).toContain('SIM_FL_SITE_');
	});
	it('legacy /monitor is a redirect/notice (no fake auth-disabled identity) and /monitoring is labelled a research tool', () => {
		const monitor = read('routes/monitor/+page.svelte');
		expect(monitor).toContain('/app/monitoring');
		expect(stripComments(monitor)).not.toMatch(/Authentication disabled|live wearable/i);
		expect(read('routes/+layout.svelte')).toContain('RESEARCH RUNTIME TOOL');
	});
});

describe('no fake metrics in the product shell', () => {
	it('/app pages contain no hard-coded dynamic-looking physiological, FL or session values', () => {
		const files = PRODUCT.filter((f) => /routes\/app/.test(rel(f)) && f.endsWith('.svelte'));
		for (const file of files) {
			const text = stripComments(readFileSync(file, 'utf-8')).replace(/<style[\s\S]*?<\/style>/g, '');
			// numbers rendered as UI text must come from {expressions}; flag literal vitals / accuracy / counts
			expect(/\b(\d{2,3}\s?(bpm|BPM)|\d{2,3}\s?%\s?(SpO|spo)|accuracy\s*[:=]?\s*0?\.\d+|F1\s*[:=]?\s*0?\.\d+|round\s*\d+\s*(of|\/)\s*\d+|\d+\s+(clients|hospitals|patients))\b/.test(text), rel(file)).toBe(false);
			expect(/global(Accuracy|F1)|activeClients/.test(text), rel(file)).toBe(false);
		}
	});
	it('no product file imports the old FL placeholder store/components', () => {
		for (const file of PRODUCT) {
			const text = stripComments(readFileSync(file, 'utf-8'));
			expect(/stores\/fl\.svelte|components\/federation\//.test(text), rel(file)).toBe(false);
		}
	});
});

describe('claim wording in product copy', () => {
	const copy = PRODUCT.filter((f) => f.endsWith('.svelte')).map((f) => stripComments(readFileSync(f, 'utf-8')).replace(/<style[\s\S]*?<\/style>/g, ''));
	it('every "diagnos*" occurrence is negated/disclaiming', () => {
		for (const text of copy) for (const m of text.matchAll(/diagnos\w*/gi)) {
			const before = text.slice(Math.max(0, m.index! - 40), m.index!).toLowerCase();
			expect(/(not|no|never|non-|n't)\s*(a\s+|an\s+)?[\w\s,/-]{0,24}$/.test(before) || /not diagnostic|non-diagnostic/.test(text.slice(Math.max(0, m.index! - 5), m.index! + 20).toLowerCase()), `unqualified: ${before}${m[0]}`).toBe(true);
		}
	});
	// Not naive substring logic: a phrase is acceptable only when the surrounding sentence qualifies it
	// (future / not / no / unavailable / unverified / never / planned).
	const QUALIFIER = /\b(future|not|no|never|unavailable|unverified|planned|without|isn't|is not|neither)\b/i;
	function unqualified(text: string, pattern: RegExp): string[] {
		const hits: string[] = [];
		for (const m of text.matchAll(new RegExp(pattern.source, 'gi'))) {
			const start = Math.max(text.lastIndexOf('.', m.index!) + 1, m.index! - 90);
			const end = Math.min(text.indexOf('.', m.index! + m[0].length) === -1 ? text.length : text.indexOf('.', m.index! + m[0].length), m.index! + m[0].length + 90);
			if (!QUALIFIER.test(text.slice(start, end))) hits.push(text.slice(start, end).trim());
		}
		return hits;
	}
	it('product copy never asserts physical hardware, on-device inference, real institutions or a PPG waveform (reviewed, qualification-aware)', () => {
		const all = copy.join('\n');
		for (const bad of [/real wearable/i, /live hardware/i, /hospital client/i, /medical device/i, /ESP32 inference/i, /on-device MODEL_V2/i, /PPG waveform connected/i, /privacy guaranteed/i, /differential privacy/i, /clinical decision/i, /disease detected/i, /patient-specific model/i]) {
			expect(unqualified(all, bad), String(bad)).toEqual([]);
		}
	});
	it('the reviewed qualified occurrences are exactly the expected disclaimers', () => {
		const all = copy.join('\n');
		expect(/real wearable[^.]*future source adapter/i.test(all)).toBe(true);
		expect(/not (a )?diagnostic or medical device|not a medical device/i.test(all + read('routes/+page.svelte'))).toBe(true);
	});
});
