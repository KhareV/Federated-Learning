import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = resolve(__dirname, '../../../..');
function walk(dir: string, out: string[] = []): string[] {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) { if (name !== '__tests__') walk(p, out); } else out.push(p);
	}
	return out;
}
const FED_FILES = [
	...walk(join(SRC, 'lib/product/federation')), ...walk(join(SRC, 'lib/components/product/federation')),
	...['federation', 'federation/clients', 'federation/rounds', 'federation/live', 'federation/privacy', 'models'].map((r) => join(SRC, `routes/app/${r}/+page.svelte`))
];
const text = (f: string) => readFileSync(f, 'utf8');
const strip = (t: string) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');

describe('federation product source audit', () => {
	it('has no user-editable control for model, base, checkpoint, candidate, hyperparameters or counts', () => {
		for (const f of FED_FILES.filter((x) => x.endsWith('.svelte'))) {
			const t = text(f);
			expect(/<input\b/i.test(t), f).toBe(false);
			expect(/<textarea\b/i.test(t), f).toBe(false);
			expect(/bind:value=\{(model|checkpoint|candidate|mu|lr|learning|batch|optimizer|epoch|clients?Count|rounds?Count)/i.test(t), f).toBe(false);
		}
		const form = text(join(SRC, 'lib/components/product/federation/RunConfigForm.svelte'));
		expect((form.match(/<select/g) ?? []).length).toBe(3);
	});
	it('never puts a token, cookie, user id or secret in a WebSocket URL', () => {
		const api = text(join(SRC, 'lib/product/api.ts'));
		const fn = api.slice(api.indexOf('export function federationSocketUrl'));
		expect(fn).not.toMatch(/token|cookie|bearer|secret|user/i);
	});
	it('has no fake dynamic metric: no accuracy/F1/AUPRC/AUROC/loss, no random or timer-driven progress', () => {
		for (const f of FED_FILES) {
			const t = strip(text(f));
			expect(/\b(accuracy|auprc|auroc|f1[ _-]?score|\bF1\b|sensitivity|specificity|loss curve|privacy score)\b/i.test(t), f).toBe(false);
			expect(/Math\.random|setInterval|requestAnimationFrame\(.*progress/.test(t), f).toBe(false);
			expect(/progress_fraction\s*[*/+-]|\*\s*100\b/.test(t), f).toBe(false); // no interpolation / percent arithmetic
		}
	});
	it('has no deploy, promote, default, inference or candidate-load control or call', () => {
		for (const f of FED_FILES) {
			const t = strip(text(f));
			expect(/infer-window|infer_window|\/infer\b|state\.bin|loadCandidate|candidateInference|runCandidate|setDefault|makeDefault|promote\(|deploy\(/i.test(t), f).toBe(false);
			if (f.endsWith('.svelte')) expect(/<button[^>]*>[^<]*(deploy|promote|make default|switch|use candidate|run inference)/i.test(t), f).toBe(false);
		}
	});
	it('keeps federation and monitoring separate: neither imports the other', () => {
		for (const m of ['lib/product/live-model.ts', 'lib/product/events.ts', 'lib/product/state.svelte.ts', 'lib/product/socket.ts']) {
			const t = text(join(SRC, m));
			if (m === 'lib/product/socket.ts') continue; // the shared bounded-retry socket machinery is intentionally reused
			expect(/federation/i.test(strip(t)) && /import .*federation/.test(t), m).toBe(false);
		}
		for (const f of FED_FILES.filter((x) => x.includes('lib/product/federation') && !x.endsWith('state.svelte.ts'))) {
			expect(/from '\.\.\/(live-model|events|state\.svelte)'/.test(text(f)), f).toBe(false);
		}
		expect(/inference\.result/.test(strip(text(join(SRC, 'lib/product/federation/live-model.ts'))))).toBe(false);
	});
	it('never draws the candidate into the released lane or live monitoring', () => {
		const lanes = text(join(SRC, 'lib/components/product/federation/ArchitectureLanes.svelte'));
		expect(/candidate[^\n]*(→|->)[^\n]*(MODEL_V2_FINAL|monitor)/i.test(lanes)).toBe(false);
		const models = text(join(SRC, 'routes/app/models/+page.svelte'));
		expect(models).toContain('never used for live monitoring');
	});
	it('contains no institution, hospital-map or privacy-overclaim copy', () => {
		for (const f of FED_FILES) {
			const t = text(f);
			expect(/HIPAA|fully private|data can never leak|cryptographically confidential|SECURE FEDERATION|PRIVATE FEDERATION|ANONYMOUS TRAINING|differentially private|world map/i.test(t), f).toBe(false);
		}
	});
	it('federation pages are not placeholders and the research pages still are', () => {
		for (const r of ['federation', 'federation/clients', 'federation/rounds', 'federation/live', 'federation/privacy', 'models']) expect(text(join(SRC, `routes/app/${r}/+page.svelte`))).not.toContain('FuturePhase');
		for (const r of ['research/ml', 'research/fl']) expect(text(join(SRC, `routes/app/${r}/+page.svelte`))).toContain('FuturePhase');
	});
});
