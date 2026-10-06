import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const read = (rel: string) => readFileSync(`src/${rel}`, 'utf8');
const landing = read('routes/+page.svelte');
const graph = read('lib/components/landing/NeuralGraph.svelte');

describe('FER-002 public landing presentation', () => {
	it('the NeuralGraph is an illustrative visualization with no unsourced statistic or live wording', () => {
		expect(graph).not.toMatch(/99\.8|LIVE EDGE|real-time|Normal \d+ BPM|Hours Unmonitored|reports\/\S+\.json/);
		expect(graph).toContain('ILLUSTRATIVE SIGNAL-FLOW GRAPH');
		expect(graph).toContain('not live telemetry');
		expect(graph).toContain('ILLUSTRATIVE VALUE (NOT LIVE)');
	});
	it('the landing page has a first-focus skip link, a focusable main target and a named navigation landmark', () => {
		expect(landing).toMatch(/<a class="skip-link" href="#top">Skip to main content<\/a>\s*\{#if preloaderMounted\}/);
		expect(landing).toContain('<main id="top" tabindex="-1">');
		expect(landing).toMatch(/<nav class="nav" aria-label="[^"]{4,}">/);
	});
	it('every perpetual decorative animation loop honours prefers-reduced-motion', () => {
		for (const rel of ['lib/components/landing/NeuralGraph.svelte', 'lib/components/landing/WatchScene.svelte', 'lib/components/signals/MultimodalStudio.svelte', 'lib/components/magic/globe/globe.svelte']) {
			expect(read(rel)).toContain('prefers-reduced-motion');
		}
	});
	it('the synthetic scenario workstation shows scenario parameters, never detections, edge privacy claims or fake live jitter', () => {
		const ws = read('lib/components/landing/ProductWorkstation.svelte');
		expect(ws).not.toMatch(/DETECTED|LOCAL ONLY|0 Bytes|setInterval|Real-Time/);
		expect(ws).toContain('SERVER-SIDE');
		expect(ws).toContain('Resting scenario (72 BPM, synthetic)');
	});
	it('data-driven actionable controls (digest copy button, run and evidence links) keep a 24px minimum target', () => {
		expect(read('lib/components/product/federation/DigestText.svelte')).toContain('min-width: 24px; min-height: 24px');
		expect(read('lib/components/product/federation/RunList.svelte')).toContain('li a { display: inline-flex; align-items: center; min-height: 24px; }');
		expect(read('routes/app/history/+page.svelte')).toContain('min-height: 24px');
	});
	it('the transient workspace loader is a main landmark with a heading and a status region', () => {
		const boot = read('routes/app/+layout.svelte');
		expect(boot).toContain('<main class="boot"><div role="status"><h1>Opening the NHM workspace…</h1></div></main>');
	});
});
