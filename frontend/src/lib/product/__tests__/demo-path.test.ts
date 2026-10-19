import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DEMO_STEPS, EVIDENCE_MODES, FORBIDDEN_CLAIMS, totalMinutes } from '../demo-path';

const routes = join(__dirname, '../../../routes');
const pageFor = (href: string) => join(routes, ...href.split('/').filter(Boolean), '+page.svelte');

describe('guided demonstration path', () => {
	it('has unique steps that each carry every field', () => {
		expect(new Set(DEMO_STEPS.map((s) => s.id)).size).toBe(DEMO_STEPS.length);
		for (const s of DEMO_STEPS) for (const key of ['title', 'does', 'understand', 'say', 'ifItFails', 'open'] as const) expect(s[key].trim().length, `${s.id}.${key}`).toBeGreaterThan(1);
	});
	it('fits a short presentation', () => {
		expect(totalMinutes()).toBeGreaterThan(6);
		expect(totalMinutes()).toBeLessThanOrEqual(10);
	});
	it('links only to pages that exist', () => {
		for (const s of DEMO_STEPS) expect(existsSync(pageFor(s.href)), s.href).toBe(true);
	});
	it('labels every step with a defined evidence mode, and replays are never called live', () => {
		for (const s of DEMO_STEPS) expect(EVIDENCE_MODES[s.mode], s.id).toBeDefined();
		expect(EVIDENCE_MODES.PREPARED_RUN.label).toMatch(/RECORDED/);
		expect(EVIDENCE_MODES.FROZEN_EVIDENCE.label).not.toMatch(/LIVE/);
		expect(EVIDENCE_MODES.RECORDED_SESSION.label).not.toMatch(/LIVE/);
	});
	it('contains no overclaiming phrase', () => {
		const text = JSON.stringify([DEMO_STEPS, EVIDENCE_MODES]);
		for (const re of FORBIDDEN_CLAIMS) expect(text, String(re)).not.toMatch(re);
	});
	it('states the hardware and cohort boundaries the audit requires', () => {
		const all = DEMO_STEPS.map((s) => `${s.does} ${s.understand} ${s.say}`).join(' ');
		expect(all).toMatch(/This is not clinical or diagnostic/);
		expect(all).toMatch(/17 to 20 samples per second/);
		expect(all).toMatch(/Physical-device verification is not claimed/);
		expect(all).toMatch(/assigned labels/);
		expect(all).toMatch(/not comparable/);
		expect(all).toMatch(/lowers performance on real MIT-BIH ECG/);
	});
	it('the forbidden-claims check can fail (mutation check)', () => {
		expect('this was clinically validated').toMatch(FORBIDDEN_CLAIMS[0]);
		expect('hardware is physically verified').toMatch(FORBIDDEN_CLAIMS[1]);
		expect('federated outperforms centralized').toMatch(FORBIDDEN_CLAIMS[2]);
	});
	it('is reachable from the Overview and from both older story pages', () => {
		const read = (p: string) => readFileSync(join(routes, p), 'utf8');
		expect(read('app/+page.svelte')).toContain('href="/app/demo"');
		expect(read('app/observatory/tour/+page.svelte')).toContain('href="/app/demo"');
		expect(read('app/observatory/storyboard/+page.svelte')).toContain('href="/app/demo"');
	});
});
