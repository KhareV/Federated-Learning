// A direct load / reload of a dynamic route must be served (HTTP 200 + SPA shell). The root layout sets prerender = true, which makes SvelteKit
// drop un-prerendered dynamic routes from the server manifest: a request for /app/history/<id> then matched nothing and returned 404.
// Every parameterised route (except the catch-all, whose 404 is correct) must therefore opt in to prerender = 'auto'.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const ROUTES = path.resolve(__dirname, '../../../routes');
function dynamicRouteDirs(dir: string, found: string[] = []): string[] {
	for (const name of readdirSync(dir)) {
		const full = path.join(dir, name);
		if (!statSync(full).isDirectory()) continue;
		if (/^\[[^.\]][^\]]*\]$/.test(name)) found.push(full);       // [param] and [[optional]], not the [...rest] catch-all
		dynamicRouteDirs(full, found);
	}
	return found;
}

describe('dynamic routes are served on direct load', () => {
	const dirs = dynamicRouteDirs(ROUTES);
	it('there are parameterised product routes to protect', () => {
		expect(dirs.map((d) => path.relative(ROUTES, d)).sort()).toEqual(['app/history/[session_id]', 'app/observatory/federation/[client_id]']);
	});
	it.each(dirs.map((d) => [path.relative(ROUTES, d), d]))("%s declares prerender = 'auto'", (_name, dir) => {
		const file = ['+page.ts', '+page.js'].map((f) => path.join(dir, f)).find((f) => existsSync(f));
		expect(file, 'a +page.ts with page options').toBeTruthy();
		expect(readFileSync(file as string, 'utf-8')).toMatch(/export const prerender = 'auto'/);
	});
	it('the catch-all keeps answering unknown paths with 404 (no prerender override)', () => {
		const catchAll = path.join(ROUTES, '[...path]');
		expect(existsSync(catchAll)).toBe(true);
		expect(['+page.ts', '+page.js'].some((f) => existsSync(path.join(catchAll, f)) && /prerender = 'auto'/.test(readFileSync(path.join(catchAll, f), 'utf-8')))).toBe(false);
	});
});
