import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { httpErrorPresentation, STATE_PRESENTATION } from '$lib/dashboard/state-presentation';

describe('model-neutral dashboard copy (V2-013 / DASHBOARD_UI_V1_4)', () => {
	it('422 presentation never claims a specific model was or was not run', () => {
		const p = httpErrorPresentation(422, 'UNUSABLE_SIGNAL_WINDOW');
		expect(p.text).toContain('No model inference was run');
		expect(p.text).not.toMatch(/MODEL_V\d/);
		expect(p.displayState).toBe('RECHECK_SENSOR');
	});

	it('exactly five public monitoring states are presented', () => {
		expect(Object.keys(STATE_PRESENTATION).sort()).toEqual([
			'CONTEXT_UNAVAILABLE',
			'NORMAL_MONITORED_PATTERN',
			'POTENTIAL_ECTOPY_ASSOCIATED_PATTERN',
			'RECHECK_SENSOR',
			'SYSTEM_ERROR'
		]);
	});

	it('route request model id is a build-time value, not a runtime selector', () => {
		const route = readFileSync('src/routes/monitoring/+page.svelte', 'utf-8');
		expect(route).toContain('VITE_NHM_REQUEST_MODEL_ID');
		expect(route).not.toMatch(/model_id:\s*'MODEL_V1'/);
		expect(route).not.toMatch(/MODEL_V1 interface window/);
		expect(route).not.toMatch(/searchParams\.get\(['"](model|model_id|checkpoint|threshold|temperature)['"]\)/);
	});
});
