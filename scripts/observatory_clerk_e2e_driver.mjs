// NHM Research Observatory connected-Clerk driver (REAL headless Chrome via CDP, REAL Clerk TEST sign-in).
// Records only booleans, statuses, counts and digests; never tokens, cookies, emails or passwords.
//   node scripts/observatory_clerk_e2e_driver.mjs <mode> <debugPort> <origin> <usersJson> <A|B> <outJson> <shotDir> [knownJson]
//   modes: a-journey | b-isolation
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const [, , MODE, debugPort, ORIGIN, USERS, WHO, OUT, SHOTS, KNOWN] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const user = JSON.parse(readFileSync(USERS))[WHO];
const known = KNOWN ? JSON.parse(KNOWN) : {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp {
	constructor(url) {
		this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
		this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
		this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const { res, rej } = this.pending.get(e.id); this.pending.delete(e.id); e.error ? rej(new Error(JSON.stringify(e.error))) : res(e.result); } else if (e.method) for (const h of this.handlers) h(e.method, e.params); };
	}
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
	on(h) { this.handlers.push(h); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const errors = [], bodies = new Map(), reqIds = new Map();
cdp.on((m, p) => {
	if (m === 'Network.requestWillBeSent') reqIds.set(p.requestId, { url: p.request.url, method: p.request.method });
	if (m === 'Network.responseReceived') { const r = reqIds.get(p.requestId); if (r) r.status = p.response.status; }
	if (m === 'Network.loadingFinished') { const r = reqIds.get(p.requestId); if (r && r.url.includes('/product/v1/')) void cdp.send('Network.getResponseBody', { requestId: p.requestId }).then((b) => { try { bodies.set(`${r.method} ${new URL(r.url).pathname}`, { status: r.status, body: JSON.parse(b.body) }); } catch { /* non-JSON */ } }).catch(() => {}); }
	if (m === 'Runtime.exceptionThrown') errors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200));
});
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(`eval: ${expression.slice(0, 80)} :: ${JSON.stringify(r.exceptionDetails).slice(0, 200)}`); return r.result.value; }
async function waitFor(expression, timeout = 120000) { const until = Date.now() + timeout; while (Date.now() < until) { let v = null; try { v = await ev(expression); } catch { /* navigating */ } if (v) return v; await sleep(150); } throw new Error(`timeout: ${expression.slice(0, 120)}`); }
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(400); };
const click = (label) => ev(`(() => { const e = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)} || x.getAttribute('aria-label') === ${JSON.stringify(label)}); if (!e || e.disabled) return false; e.click(); return true; })()`);
const body = () => ev('document.body.innerText');
const lastBody = (re) => { let hit = null; for (const [k, v] of bodies) if (re.test(k)) hit = v; return hit; };
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
// Authenticated in-page fetch through the signed-in Clerk session. The token never leaves the page and is never recorded.
const api = (path, method = 'GET', payload = null) => ev(`(async () => { const t = await window.Clerk?.session?.getToken(); const r = await fetch(${JSON.stringify('/product/v1' + '')} + ${JSON.stringify(path)}, { method: ${JSON.stringify(method)}, headers: { ...(t ? { Authorization: 'Bearer ' + t } : {}), 'Content-Type': 'application/json' }, body: ${JSON.stringify(payload ? JSON.stringify(payload) : null)} }); let b = null; try { b = await r.json(); } catch { /* empty */ } return { status: r.status, body: b, hadToken: !!t }; })()`);
await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
const out = { mode: MODE, who: WHO, steps: [] };
const step = (name, data = {}) => out.steps.push({ step: name, ...data });
const t0 = Date.now();

async function clerkSignIn() {
	await goto('/sign-in');
	await waitFor(`!!document.querySelector('input[name=identifier]')`, 60000);
	await ev(`document.querySelector('input[name=identifier]').focus()`); await cdp.send('Input.insertText', { text: user.email });
	await sleep(400); await click('Continue');
	await waitFor(`!!document.querySelector('input[name=password]')`, 30000); await sleep(1500);
	await ev(`document.querySelector('input[name=password]').focus()`); await cdp.send('Input.insertText', { text: user.password });
	await sleep(600); await click('Continue'); await sleep(4000);
	if ((await ev('location.href')).includes('/sign-in') && /Enter your password/.test(await body())) await click('Continue');
	let trust = false; const until = Date.now() + 60000;
	for (;;) {
		const href = await ev('location.href'); const t = await body();
		if (!href.includes('/sign-in')) break;
		if (!trust && (href.includes('client-trust') || /Check your email|verification code/i.test(t))) { trust = true; await ev(`document.querySelector('input').focus()`); for (const ch of '424242') { await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch }); await sleep(120); } }
		if (Date.now() > until) { await shot('signin_timeout'); throw new Error('signin timeout: ' + href.replace(/[?#].*/, '') + ' :: ' + t.replace(/\s+/g, ' ').slice(0, 240)); }
		await sleep(400);
	}
	await goto('/app'); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000); await sleep(800);
	const sys = lastBody(/GET \/product\/v1\/system$/), me = lastBody(/GET \/product\/v1\/me$/);
	step('signin', { clientTrustVerificationUsed: trust, system: { auth_provider: sys?.body?.auth_provider, demo_mode: sys?.body?.demo_mode, model_id: sys?.body?.model_id }, me: { status: me?.status, auth_provider: me?.body?.auth_provider, demo_mode: me?.body?.demo_mode, user_id_is_clerk_shaped: /^user_/.test(me?.body?.user_id ?? ''), user_id_is_demo: /^demo:/.test(me?.body?.user_id ?? '') }, clerkGlobal: await ev(`typeof window.Clerk !== 'undefined'`) });
}

const redact = (r) => ({ status: r.status });
if (MODE === 'a-journey') {
	await clerkSignIn();
	const system = (await api('/system')).body;
	step('system', { auth_provider: system.auth_provider, demo_mode: system.demo_mode, model_id: system.model_id, calibration_id: system.calibration_id });
	// Owned monitoring session on the virtual wearable, with explicit opt-in live capture armed before start.
	const dev = await api('/devices/simulated', 'POST', { scenario_id: 'NORMAL_MONITORING' });
	const did = dev.body.device_id;
	await api(`/devices/${did}/scan`, 'POST'); await api(`/devices/${did}/connect`, 'POST');
	const sess = await api('/sessions', 'POST', { device_id: did, scenario_id: 'NORMAL_MONITORING' });
	const sid = sess.body.session_id;
	const arm = await api(`/observatory/sessions/${sid}/capture/0`, 'POST');
	await api(`/sessions/${sid}/start`, 'POST');
	let state = ''; for (let i = 0; i < 240 && state !== 'COMPLETED' && state !== 'FAILED'; i++) { await sleep(1000); state = (await api(`/sessions/${sid}`)).body?.state; }
	const cap = await api(`/observatory/sessions/${sid}/capture`);
	step('monitoring', { session_state: state, arm_status: arm.status, capture_status: cap.status, classification: cap.body?.classification, stages: cap.body?.stages?.length, persisted_model: cap.body?.persisted_inference?.model_id ?? null });
	await goto('/app/observatory'); await waitFor(`!!document.querySelector('figure.signal')`, 90000); await shot('observatory_landing_1440');
	step('observatory-page', { charts: await ev(`document.querySelectorAll('figure.signal').length`), overflow: await ev('document.documentElement.scrollWidth > innerWidth') });
	// Genuine LIVE_RUN owned by this Clerk user.
	const run = await api('/federation/runs', 'POST', { run_type: 'LIVE_RUN', algorithm: 'FEDAVG', secagg_mode: 'SECAGG_SHADOW', planned_rounds: 3, scenario_id: 'FL_SINGLE_RUN' });
	const rid = run.body?.run_id; await api(`/federation/runs/${rid}/start`, 'POST');
	let status = ''; for (let i = 0; i < 300 && status !== 'COMPLETED' && status !== 'FAILED'; i++) { await sleep(2000); status = (await api(`/federation/runs/${rid}`)).body?.status; }
	const contrib = (await api(`/observatory/federation/runs/${rid}/contributions`)).body;
	step('federation', { run_status: status, rounds: contrib.rounds.length, per_round: contrib.rounds.map((r) => ({ basis: r.acceptance_basis, accepted: r.accepted_update_count, examples: r.accepted_example_total, clients: r.clients.length, diagnostics: r.clients.filter((c) => c.training_diagnostic).length })), total_accepted: contrib.rounds.reduce((a, r) => a + (r.accepted_update_count ?? 0), 0) });
	const models = (await api('/models')).body; step('candidate', { released: models.released_default_model_id, digests: models.capstone_fl_candidates.map((c) => c.state_digest), deployed: models.capstone_fl_candidates.map((c) => c.production_deployed) });
	await goto(`/app/federation/live?run=${rid}`); await waitFor(`document.querySelectorAll('[data-client]').length === 8 && (document.querySelector('[data-testid="run-status"]')?.textContent ?? '').includes('COMPLETED')`, 90000); await sleep(1200);
	step('owner-bound-live', { ownerCards: await ev(`document.querySelectorAll('[data-role="AUTHENTICATED_OWNER"]').length`), peers: await ev(`document.querySelectorAll('[data-role="SYNTHETIC_PEER"]').length`), myEdge: await ev(`(document.body.innerText.match(/MY EDGE CLIENT/g) || []).length`), owner: await ev(`document.querySelector('[data-role="AUTHENTICATED_OWNER"]')?.getAttribute('data-client')`) }); await shot('live_owner_bound_1440');
	await goto('/app/observatory/federation'); await waitFor(`document.querySelectorAll('.roster button').length === 8`, 90000);
	await ev(`(() => { const d = document.querySelector('details.matrix'); if (d) d.open = true; })()`); await sleep(800);
	step('observatory-federation', { roster: await ev(`document.querySelectorAll('.roster button').length`), directLabel: await ev(`document.body.innerText.includes('directly observed')`), overflow: await ev('document.documentElement.scrollWidth > innerWidth') }); await shot('observatory_federation_1440');
	await ev(`document.querySelector('[data-testid="fedavg-math"]')?.scrollIntoView()`);
	step('aggregation-views', { math: await ev(`!!document.querySelector('[data-testid="fedavg-math"]')`), chained: await ev(`document.querySelectorAll('[data-testid="state-lineage"] li').length`), chainedOk: await ev(`(document.querySelector('[data-testid="state-lineage"]')?.innerText.match(/starts from the committed state/g) || []).length`), whyFast: await ev(`(document.querySelector('[data-testid="why-fast"]')?.innerText ?? '').includes('24 local training calls')`), unchainedMarks: await ev(`(document.body.innerText.match(/does not match the previous committed state/g) || []).length`) }); await shot('observatory_aggregation_1440');
	await goto('/app/federation/clients'); await waitFor(`document.querySelectorAll('[data-client]').length === 8`, 60000);
	step('global-clients-unbound', { myEdge: await ev(`(document.body.innerText.match(/MY EDGE CLIENT/g) || []).length`) });
	// Sign-out must end backend access; no silent DemoAuth fallback.
	await goto('/app'); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000);
	const signedOut = await click('Sign out'); await sleep(3000);
	const afterHref = await ev('location.pathname');
	const anon = await ev(`fetch('/product/v1/observatory/scenarios').then((r) => r.status)`);
	step('sign-out', { clicked: signedOut, path: afterHref, anonymous_observatory_status: anon });
	out.known = { session_id: sid, run_id: rid };
}
if (MODE === 'b-isolation') {
	await clerkSignIn();
	const me = (await api('/me')).body;
	const probes = {};
	for (const [name, path, method] of [['session_capture', `/observatory/sessions/${known.session_id}/capture`, 'GET'], ['session_window', `/observatory/sessions/${known.session_id}/windows/0`, 'GET'], ['arm_capture', `/observatory/sessions/${known.session_id}/capture/0`, 'POST'], ['run_contributions', `/observatory/federation/runs/${known.run_id}/contributions`, 'GET'], ['run', `/federation/runs/${known.run_id}`, 'GET']]) probes[name] = (await api(path, method)).status;
	const own = await api('/observatory/federation/cohort');
	const runs = (await api('/federation/runs')).body;
	step('isolation', { b_is_clerk: /^user_/.test(me.user_id ?? ''), probes, own_cohort_status: own.status, a_run_visible_in_b_list: (runs ?? []).some((r) => r.run_id === known.run_id) });
	await goto('/app/observatory/federation'); await waitFor(`document.querySelectorAll('.roster button').length === 8`, 90000);
	step('b-federation-page', { myEdge: await ev(`(document.body.innerText.match(/MY EDGE CLIENT/g) || []).length`) }); await shot('b_observatory_federation_1440');
}
out.console_errors = errors.filter((e) => !/Failed to load resource|clerk-telemetry|ERR_/i.test(e));
out.elapsed_s = Math.round((Date.now() - t0) / 1000);
writeFileSync(OUT, JSON.stringify(out, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
