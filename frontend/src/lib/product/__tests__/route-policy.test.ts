import { describe, expect, it } from 'vitest';
import { LEGACY_REDIRECTS, legacyRedirect } from '../route-policy';

describe('LEGACY_ROUTE_POLICY_V1', () => {
	it('retires the audit examples to truthful current routes', () => {
		expect(legacyRedirect('/fl/overview')).toBe('/app/federation');
		expect(legacyRedirect('/fl/personal-models')).toBe('/app/federation');
		expect(legacyRedirect('/ai/insights')).toBe('/app/research/ml');
		expect(legacyRedirect('/overview')).toBe('/app');
	});
	it('matches exactly: no prefix or substring overreach, trailing slash normalised', () => {
		expect(legacyRedirect('/overview/')).toBe('/app');
		expect(legacyRedirect('/overviews')).toBeNull();
		expect(legacyRedirect('/app/overview')).toBeNull();
		expect(legacyRedirect('/fl')).toBeNull();
		expect(legacyRedirect('/fl/overview/extra')).toBeNull();
	});
	it('never redirects a current or retained route', () => {
		for (const path of ['/', '/sign-in', '/app', '/app/about', '/app/federation/live', '/app/history', '/app/research/fl', '/monitor', '/monitoring']) expect(legacyRedirect(path)).toBeNull();
	});
	it('only targets same-origin canonical /app routes, with no chains or loops', () => {
		for (const [from, to] of Object.entries(LEGACY_REDIRECTS)) {
			expect(to.startsWith('/app')).toBe(true);
			expect(to.includes('//') || to.includes(':')).toBe(false);
			expect(to).not.toBe(from);
			expect(legacyRedirect(to)).toBeNull();
		}
	});
});
