// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { ProductApiError, createProductClient, liveSocketUrl, kindForStatus } from '../api';
import { FrontendAuth, type ClerkLike } from '../auth';
import { DEMO_IDENTITY, fakeBackend, memoryStorage, systemInfo } from './support';

function jsonResponse(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('product client', () => {
	it('uses same-origin /product/v1 and implements only CAP-004 routes (no /v1/infer-window, no model field)', async () => {
		const seen: { url: string; init: RequestInit }[] = [];
		const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
			seen.push({ url, init });
			return jsonResponse([]);
		}) as unknown as typeof fetch;
		const c = createProductClient({ fetchImpl });
		await c.system(); await c.me(); await c.devices();
		await c.createSimulatedDevice('MIXED_MONITORING_SESSION'); await c.scan('D'); await c.connect('D'); await c.disconnect('D');
		await c.createSession('D', 'MIXED_MONITORING_SESSION'); await c.sessions(); await c.session('S'); await c.startSession('S'); await c.stopSession('S');
		expect(seen.map((s) => `${s.init.method} ${s.url}`)).toEqual([
			'GET /product/v1/system', 'GET /product/v1/me', 'GET /product/v1/devices',
			'POST /product/v1/devices/simulated', 'POST /product/v1/devices/D/scan', 'POST /product/v1/devices/D/connect',
			'POST /product/v1/devices/D/disconnect', 'POST /product/v1/sessions', 'GET /product/v1/sessions',
			'GET /product/v1/sessions/S', 'POST /product/v1/sessions/S/start', 'POST /product/v1/sessions/S/stop'
		]);
		expect(seen.some((s) => s.url.includes('infer-window') || s.url.startsWith('/v1'))).toBe(false);
		const bodies = seen.map((s) => (s.init.body ? JSON.parse(String(s.init.body)) : null)).filter(Boolean);
		expect(bodies).toEqual([{ scenario_id: 'MIXED_MONITORING_SESSION' }, { device_id: 'D', scenario_id: 'MIXED_MONITORING_SESSION' }]);
		for (const b of bodies) expect(Object.keys(b).some((k) => /model|checkpoint|threshold|calibration/i.test(k))).toBe(false);
	});
	it('sends Authorization: Bearer only when a token provider yields one, and stores nothing', async () => {
		const local = memoryStorage(), sessionS = memoryStorage();
		vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', sessionS);
		const headers: Record<string, string>[] = [];
		const fetchImpl = (async (_u: string, init: RequestInit) => { headers.push(init.headers as Record<string, string>); return jsonResponse({}); }) as unknown as typeof fetch;
		await createProductClient({ fetchImpl }).system();
		await createProductClient({ fetchImpl, getToken: async () => null }).system();
		await createProductClient({ fetchImpl, getToken: async () => 'tok-abc' }).system();
		expect(headers[0].Authorization).toBeUndefined();
		expect(headers[1].Authorization).toBeUndefined();
		expect(headers[2].Authorization).toBe('Bearer tok-abc');
		expect(local.writes + sessionS.writes).toBe(0);
		expect(document.cookie).not.toContain('tok-abc');
	});
	it('maps product errors honestly (401/403/404/409/400/transport)', async () => {
		const mk = (status: number) => createProductClient({ fetchImpl: (async () => jsonResponse({ error: { code: 'X', message: 'm' } }, status)) as unknown as typeof fetch });
		const kinds: Record<number, string> = { 401: 'AUTHENTICATION_REQUIRED', 403: 'NOT_PERMITTED', 404: 'UNAVAILABLE', 409: 'INVALID_LIFECYCLE_STATE', 400: 'INVALID_REQUEST' };
		for (const [status, kind] of Object.entries(kinds)) {
			await expect(mk(Number(status)).me()).rejects.toMatchObject({ status: Number(status), kind });
		}
		await expect(createProductClient({ fetchImpl: (async () => { throw new TypeError('down'); }) as unknown as typeof fetch }).me()).rejects.toMatchObject({ kind: 'TRANSPORT' });
		expect(kindForStatus(500)).toBe('BACKEND_ERROR');
		const err = new ProductApiError(409, 'INVALID_LIFECYCLE_STATE', 'INVALID_STATE', 'x');
		expect(err.message).not.toMatch(/arrhythm|diagnos|patient|disease/i);
	});
	it('builds a same-origin WebSocket URL that carries no token', () => {
		expect(liveSocketUrl('SESS-1', { protocol: 'http:', host: 'localhost:5173' })).toBe('ws://localhost:5173/product/v1/sessions/SESS-1/live');
		expect(liveSocketUrl('SESS-1', { protocol: 'https:', host: 'x.example' })).toBe('wss://x.example/product/v1/sessions/SESS-1/live');
		expect(liveSocketUrl('SESS-1', { protocol: 'http:', host: 'h' })).not.toMatch(/token|\?|Bearer/i);
	});
});

function clerkStub(signedIn: boolean): ClerkLike & { loads: number; signOuts: number; tokens: number } {
	const stub = {
		loads: 0, signOuts: 0, tokens: 0,
		session: signedIn ? { getToken: async () => { stub.tokens += 1; return 'clerk-session-token'; } } : null,
		async load() { stub.loads += 1; },
		mountSignIn() {}, unmountSignIn() {},
		async signOut() { stub.signOuts += 1; (stub as { session: unknown }).session = null; }
	};
	return stub as unknown as ClerkLike & { loads: number; signOuts: number; tokens: number };
}

describe('CAPSTONE_FRONTEND_AUTH_V1 bootstrap', () => {
	it('DEMO backend: never initialises or imports Clerk; /me supplies the demo identity', async () => {
		const loadClerk = vi.fn();
		const backend = fakeBackend(systemInfo({ auth_provider: 'DEMO', demo_mode: true }));
		const auth = new FrontendAuth({ createClient: () => backend, loadClerk, publishableKey: 'pk_test_x' });
		const state = await auth.bootstrap();
		expect(state.mode).toBe('DEMO');
		expect(state.phase).toBe('SIGN_IN_REQUIRED');
		expect(loadClerk).not.toHaveBeenCalled();
		expect(auth.clerkWasInitialised).toBe(false);
		const entered = await auth.enterDemo();
		expect(entered.phase).toBe('AUTHENTICATED');
		expect(entered.identity).toEqual(DEMO_IDENTITY);
		expect(backend.calls).toEqual(['system', 'me']);
		expect(loadClerk).not.toHaveBeenCalled();
	});
	it('mode is decided by the backend /system, never by a frontend toggle', async () => {
		const loadClerk = vi.fn(async () => clerkStub(false));
		const auth = new FrontendAuth({ createClient: () => fakeBackend(systemInfo({ auth_provider: 'CLERK', demo_mode: false })), loadClerk, publishableKey: 'pk_test_x' });
		expect((await auth.bootstrap()).mode).toBe('CLERK');
		expect(await auth.enterDemo()).toMatchObject({ mode: 'CLERK', phase: 'SIGN_IN_REQUIRED' }); // cannot switch to demo
		expect(auth.state.identity).toBeNull();
	});
	it('CLERK backend: initialises ClerkJS (mocked official boundary) and sends the session token as Bearer', async () => {
		const clerk = clerkStub(true);
		const authHeaders: (string | undefined)[] = [];
		const fetchImpl = (async (url: string, init: RequestInit) => {
			authHeaders.push((init.headers as Record<string, string>).Authorization);
			return jsonResponse(url.endsWith('/system') ? systemInfo({ auth_provider: 'CLERK', demo_mode: false }) : { ...DEMO_IDENTITY, auth_provider: 'CLERK', demo_mode: false, user_id: 'user_clerk_1' });
		}) as unknown as typeof fetch;
		const local = memoryStorage(), sessionS = memoryStorage();
		vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', sessionS);
		const auth = new FrontendAuth({ createClient: (getToken) => createProductClient({ fetchImpl, getToken }), loadClerk: async () => clerk, publishableKey: 'pk_test_x' });
		const state = await auth.bootstrap();
		expect(clerk.loads === 0).toBe(true); // load() is the loader's job; the abstraction used the provided instance
		expect(auth.clerkWasInitialised).toBe(true);
		expect(state.phase).toBe('AUTHENTICATED');
		expect(state.identity?.user_id).toBe('user_clerk_1');
		expect(authHeaders.at(-1)).toBe('Bearer clerk-session-token');
		expect(local.writes + sessionS.writes).toBe(0); // token never persisted
		expect(JSON.stringify(auth.state)).not.toContain('clerk-session-token');
	});
	it('CLERK backend with a missing publishable key shows AUTHENTICATION UNAVAILABLE and does not fall back to Demo', async () => {
		const loadClerk = vi.fn();
		const backend = fakeBackend(systemInfo({ auth_provider: 'CLERK', demo_mode: false }));
		const auth = new FrontendAuth({ createClient: () => backend, loadClerk, publishableKey: null });
		const state = await auth.bootstrap();
		expect(state.phase).toBe('AUTHENTICATION_UNAVAILABLE');
		expect(state.error).toMatch(/publishable key/i);
		expect(state.identity).toBeNull();
		expect(loadClerk).not.toHaveBeenCalled();
		expect(backend.calls).toEqual(['system']); // no /me loop, no protected requests
	});
	it('CLERK backend whose Clerk SDK fails to initialise never falls back to Demo', async () => {
		const backend = fakeBackend(systemInfo({ auth_provider: 'CLERK', demo_mode: false }));
		const auth = new FrontendAuth({ createClient: () => backend, loadClerk: async () => { throw new Error('network down'); }, publishableKey: 'pk_test_x' });
		const state = await auth.bootstrap();
		expect(state.phase).toBe('AUTHENTICATION_UNAVAILABLE');
		expect(state.mode).toBe('CLERK');
		expect(state.identity).toBeNull();
		expect(backend.calls).toEqual(['system']);
		expect((await auth.restore()).phase).toBe('AUTHENTICATION_UNAVAILABLE');
	});
	it('sign-out clears the identity state and signs the Clerk session out', async () => {
		const clerk = clerkStub(true);
		const backend = fakeBackend(systemInfo({ auth_provider: 'CLERK', demo_mode: false }));
		const auth = new FrontendAuth({ createClient: () => backend, loadClerk: async () => clerk, publishableKey: 'pk_test_x' });
		await auth.bootstrap();
		expect(auth.state.phase).toBe('AUTHENTICATED');
		await auth.signOut();
		expect(clerk.signOuts).toBe(1);
		expect(auth.state.identity).toBeNull();
		expect(auth.state.phase).toBe('SIGN_IN_REQUIRED');
	});
	it('an unreachable backend is reported as such (no identity invented)', async () => {
		const backend = fakeBackend();
		backend.system = async () => { throw new ProductApiError(0, 'TRANSPORT', null, 'ECONNREFUSED'); };
		const auth = new FrontendAuth({ createClient: () => backend });
		expect((await auth.bootstrap()).phase).toBe('BACKEND_UNREACHABLE');
		expect(auth.state.identity).toBeNull();
	});
});
