import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const route = (name: string) => readFileSync(path.join(process.cwd(), 'src/routes/app', name, '+page.svelte'), 'utf8');
const component = (name: string) => readFileSync(path.join(process.cwd(), 'src/lib/components/product', name), 'utf8');

describe('UI-ENH-003 final presentation boundaries', () => {
	it('device keeps the simulated-only and physical-hardware boundary visible', () => {
		const text = route('device');
		expect(text).toContain('SIMULATED ONLY');
		expect(text).toContain('PHYSICAL HARDWARE: NOT CONNECTED / NOT IMPLEMENTED');
		expect(text).toContain('CONTINUE TO MONITORING');
	});
	it('history preserves the table while offering full-fact mobile cards', () => {
		const text = route('history');
		expect(text).toContain('data-testid="session-table"');
		expect(text).toContain('class="mobile-list"');
		for (const label of ['Scenario', 'Model', 'Device', 'Started', 'Ended', 'VIEW EVIDENCE']) expect(text).toContain(label);
	});
	it('session evidence keeps both time domains and null waveform gaps', () => {
		const text = route('history/[session_id]');
		expect(text).toContain('SOURCE DOMAIN');
		expect(text).toContain('PRODUCT CLOCK');
		expect(text).toContain('if (value === null)');
		expect(text).toContain('TECHNICAL EVENT DETAILS');
	});
	it('privacy and run list do not imply private or new training on replay', () => {
		const privacy = route('federation/privacy');
		const list = component('federation/RunList.svelte');
		expect(privacy).toContain('Authoritative aggregation remains PLAIN');
		expect(privacy).toContain('No differential privacy.');
		expect(privacy).toContain('No production security certification.');
		expect(list).toContain('REPLAY — NO TRAINING');
		expect(list).toContain('TECHNICAL RUN EVIDENCE');
	});
	it('system raw response and about claim boundaries remain available', () => {
		expect(route('system')).toContain('RAW SYSTEM RESPONSE');
		const about = route('about');
		expect(about).toContain('not diagnostic');
		expect(about).toContain('monitoring sessions are never federation data');
	});
});
