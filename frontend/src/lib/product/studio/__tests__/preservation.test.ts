// The original Federation Studio is the visual authority: compare the CURRENT pages with their source at the pre-Studio commit 06bd9a0 (read from git history).
// Everything the original rendered must still be there, in the same order, with the same styling rules; the Studio only adds sections.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = path.resolve(__dirname, '../../../../../..');
const ORIGINAL = '06bd9a0';
const original = (p: string) => execFileSync('git', ['show', `${ORIGINAL}:${p}`], { cwd: ROOT, maxBuffer: 1 << 24 }).toString();
const current = (p: string) => readFileSync(path.join(ROOT, p), 'utf-8');
const testIds = (s: string) => [...s.matchAll(/data-testid=["']([^"'{]+)["']/g)].map((m) => m[1]);
const eyebrows = (s: string) => [...s.matchAll(/<Panel eyebrow="([^"]+)"/g)].map((m) => m[1]);
const imports = (s: string) => [...s.matchAll(/import\s+[^;]*?from\s+'([^']+)'/g)].map((m) => m[1]);
const rules = (s: string) => (s.match(/<style>([\s\S]*?)<\/style>/)?.[1] ?? '').split('}').map((r) => r.replace(/\s+/g, ' ').trim()).filter(Boolean);
const isSubsequence = (needle: string[], hay: string[]) => { let i = 0; for (const x of hay) if (x === needle[i]) i++; return i === needle.length; };

describe.each([
	'frontend/src/routes/app/federation/live/+page.svelte',
	'frontend/src/routes/app/federation/+page.svelte',
	'frontend/src/routes/app/federation/rounds/+page.svelte'
])('%s keeps everything the original page rendered', (file) => {
	const before = original(file), after = current(file);
	it('every original data-testid is still present', () => {
		for (const id of new Set(testIds(before))) expect(after, id).toContain(`data-testid="${id}"`);
	});
	it('every original panel is still present, in the original order', () => {
		expect(isSubsequence(eyebrows(before), eyebrows(after)), `${eyebrows(before)} vs ${eyebrows(after)}`).toBe(true);
	});
	it('every original import (component, store, parser) is still used', () => {
		// the entry page now reaches the unchanged RunConfigForm through the round-count starter (asserted below)
		for (const i of imports(before).filter((x) => !(file.endsWith('federation/+page.svelte') && x.endsWith('RunConfigForm.svelte')))) expect(after, i).toContain(i);
	});
	it('every original style rule is still defined (no restyling of the original page)', () => {
		const now = new Set(rules(after).map((r) => r.replace(/\s*;\s*$/, '')));
		const missing = rules(before).filter((r) => !now.has(r.replace(/\s*;\s*$/, '')));
		expect(missing).toEqual([]);
	});
});

// RECORDED-HARDWARE PROVISION (reviewed, additive): these two components gained ONE optional `dataSource` prop so the SAME Live page can show a recorded-hardware
// run (client ids, card tag, buffer/model wording). Synthetic runs render exactly as before (default 'SYNTHETIC'). Every original test id and style rule must remain,
// and the reviewed bytes are pinned so any further drift fails here.
const REVIEWED_HARDWARE_PROVISION: Record<string, string> = {
	'frontend/src/lib/components/product/federation/ClientGrid.svelte': '573ec801e90e186dde585aa91903f121e93c0f0d3cf254c3a3d8209f160a5115',
	'frontend/src/lib/components/product/federation/ClientDetailPanel.svelte': 'bc1e08bcc0f4e62817da65a166f43367eadf9d7761dd0a374c3d58881a4542d2'
};
describe('recorded-hardware provision keeps the original component design', () => {
	it.each(Object.keys(REVIEWED_HARDWARE_PROVISION))('%s: original test ids and style rules are intact and the reviewed bytes are pinned', (file) => {
		const before = original(file), after = current(file);
		for (const id of new Set(testIds(before))) expect(after, id).toContain(`data-testid="${id}"`);
		const now = new Set(rules(after).map((r) => r.replace(/\s*;\s*$/, '')));
		expect(rules(before).filter((r) => !now.has(r.replace(/\s*;\s*$/, '')))).toEqual([]);
		expect(createHash('sha256').update(after).digest('hex')).toBe(REVIEWED_HARDWARE_PROVISION[file]);
	});
});

describe('the original network components and the owner-binding rule are untouched', () => {
	it.each([
		'frontend/src/lib/components/product/federation/ProcessStepper.svelte', 'frontend/src/lib/components/product/federation/RoundProgress.svelte',
		'frontend/src/lib/components/product/federation/ModelStateTransition.svelte', 'frontend/src/lib/components/product/federation/CandidateLifecycle.svelte', 'frontend/src/lib/components/product/federation/FederationTimeline.svelte',
		'frontend/src/lib/components/product/federation/RunConfigForm.svelte', 'frontend/src/lib/components/product/federation/TechnicalEvidence.svelte',
		'frontend/src/lib/product/federation/participation.ts', 'frontend/src/lib/product/federation/live-model.ts', 'frontend/src/lib/product/federation/events.ts', 'frontend/src/lib/product/federation/presentation.ts'
	])('%s is byte-identical to the original', (file) => {
		expect(current(file)).toBe(original(file));
	});
	it('the 3-round default still renders the ORIGINAL run form (inside the round-count starter)', () => {
		expect(current('frontend/src/lib/components/product/studio/StudioRunStarter.svelte')).toContain("import RunConfigForm from '$lib/components/product/federation/RunConfigForm.svelte'");
		expect(current('frontend/src/lib/components/product/studio/StudioRunStarter.svelte')).toContain('<RunConfigForm {disabled} {liveBlocked} {backendEnabled} onSubmit={onStartThree} />');
	});
	it('the live page still derives the star from the unchanged ownerBoundClientId rule', () => {
		expect(current('frontend/src/routes/app/federation/live/+page.svelte')).toContain('ownerBoundClientId(product.authState.system?.auth_provider, v.runType ?? fed.run?.run_type)');
	});
});
