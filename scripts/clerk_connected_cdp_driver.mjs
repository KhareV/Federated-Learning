// CLERK-LIVE-001 real-browser driver: REAL headless Chrome (CDP) + REAL Clerk TEST-instance sign-in + the real connected stack.
// No mock Clerk, no injected tokens, no cookie copying. REST bodies/status are observed from the APP's OWN requests
// (Network domain); bearer/cookie presence is recorded as booleans only (never values). External hosts are RECORDED (Clerk needs the network).
//   node scripts/clerk_connected_cdp_driver.mjs <mode> <debugPort> <origin> <usersJson> <who A|B> <outJson> <shotDir> [sessionId runId]
//   modes: a-journey | b-isolation | a-return | signin-only
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const [, , MODE, debugPort, ORIGIN, USERS, WHO, OUT, SHOTS, KNOWN_SESSION, KNOWN_RUN] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const user = JSON.parse(readFileSync(USERS))[WHO]; user.label = `TEST_USER_${WHO}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp {
	constructor(url) {
		this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
		this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
		this.ws.onmessage = (m) => {
			const e = JSON.parse(m.data);
			if (e.id && this.pending.has(e.id)) { const { res, rej } = this.pending.get(e.id); this.pending.delete(e.id); e.error ? rej(new Error(JSON.stringify(e.error))) : res(e.result); }
			else if (e.method) for (const h of this.handlers) h(e.method, e.params);
		};
	}
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
	on(h) { this.handlers.push(h); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const hosts = new Set(), errors = [], rest = [], sockets = new Map(), reqIds = new Map(), bodies = new Map();
const probes = [];                // Fetch-level probes: rewrite ONE app request (keeping the app's real Authorization) to a cross-user target
let probeQueue = [];
const redact = (u) => u.replace(/([?&](token|__session|jwt|access_token)=)[^&]+/gi, '$1<REDACTED>');
const isJwtLike = (s) => /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\./.test(s);
cdp.on((m, p) => {
	if (m === 'Network.requestWillBeSent') { try { hosts.add(new URL(p.request.url).host); } catch { /* data: */ } reqIds.set(p.requestId, { url: p.request.url, method: p.request.method }); }
	if (m === 'Network.requestWillBeSentExtraInfo') { const r = reqIds.get(p.requestId); if (r) { const h = Object.fromEntries(Object.entries(p.headers).map(([k, v]) => [k.toLowerCase(), v])); r.bearer = /^Bearer\s+\S{20,}/.test(h.authorization ?? ''); r.bearerJwtShape = isJwtLike(h.authorization ?? ''); r.cookieSession = /(^|;\s*)__session=/.test(h.cookie ?? ''); } }
	if (m === 'Network.responseReceived') {
		for (const q of probes) if (q.networkId && q.networkId === p.requestId) { q.status = p.response.status; q.responseUrl = p.response.url.replace(/^https?:\/\/[^/]+/, ''); }
		const r = reqIds.get(p.requestId);
		if (r) { r.status = p.response.status; r.mime = p.response.mimeType; r.url = p.response.url; if (new URL(r.url).pathname.startsWith('/product/v1/')) rest.push(r); }
	}
	if (m === 'Network.loadingFinished') { const r = reqIds.get(p.requestId); if (r && r.url.includes('/product/v1/')) void cdp.send('Network.getResponseBody', { requestId: p.requestId }).then((b) => { const k = `${r.method} ${new URL(r.url).pathname}${new URL(r.url).search}`; try { bodies.set(k, { status: r.status, body: JSON.parse(b.body) }); } catch { bodies.set(k, { status: r.status, body: null }); } }).catch(() => {}); }
	if (m === 'Network.webSocketCreated') sockets.set(p.requestId, { url: redact(p.url), pathname: new URL(p.url.replace(/^ws/, 'http')).pathname, urlHasToken: /[?&](token|__session|jwt|access_token)=|eyJ/i.test(p.url), handshakeStatus: null, framesReceived: 0, cookieSessionSent: null, closed: false });
	if (m === 'Network.webSocketWillSendHandshakeRequest') { const s = sockets.get(p.requestId); if (s) s.cookieSessionSent = /(^|;\s*)__session=/.test(Object.fromEntries(Object.entries(p.request.headers).map(([k, v]) => [k.toLowerCase(), v])).cookie ?? ''); }
	if (m === 'Network.webSocketHandshakeResponseReceived') { const s = sockets.get(p.requestId); if (s) s.handshakeStatus = p.response.status; }
	if (m === 'Network.webSocketFrameReceived') { const s = sockets.get(p.requestId); if (s) { s.framesReceived++; if (s.framesReceived <= 1) s.firstFrameKind = (() => { try { return JSON.parse(p.response.payloadData).kind ?? null; } catch { return null; } })(); } }
	if (m === 'Network.webSocketClosed') { const s = sockets.get(p.requestId); if (s) s.closed = true; }
	if (m === 'Fetch.requestPaused') {
		const q = probeQueue.find((x) => !x.done && x.match(p.request));
		if (q) { q.done = true; q.networkId = p.networkId ?? p.requestId; q.rewrittenUrl = new URL(q.to, ORIGIN).toString(); q.rewrittenMethod = q.method; q.bearerKept = /^Bearer\s+\S{20,}/.test(p.request.headers.Authorization ?? p.request.headers.authorization ?? ''); void cdp.send('Fetch.continueRequest', { requestId: p.requestId, url: q.rewrittenUrl, method: q.method, ...(q.postData ? { postData: Buffer.from(q.postData).toString('base64') } : {}) }).catch((e) => errors.push(`PROBE:${e}`)); }
		else void cdp.send('Fetch.continueRequest', { requestId: p.requestId }).catch(() => {});
	}
	if (m === 'Runtime.exceptionThrown') errors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200));
	if (m === 'Runtime.consoleAPICalled' && p.type === 'error') errors.push(p.args.map((a) => a.value ?? a.description).join(' ').slice(0, 200));
});
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
if (MODE === 'b-isolation') await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/product/v1/*', requestStage: 'Request' }] });
async function ev(expression) {
	const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
	if (r.exceptionDetails) throw new Error(`eval: ${expression.slice(0, 80)} :: ${JSON.stringify(r.exceptionDetails).slice(0, 200)}`);
	return r.result.value;
}
async function waitFor(expression, timeout = 120000) {
	const until = Date.now() + timeout;
	while (Date.now() < until) { let v = null; try { v = await ev(expression); } catch { /* navigating */ } if (v) return v; await sleep(100); }
	throw new Error(`timeout: ${expression.slice(0, 120)}`);
}
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(300); };
const click = (label) => ev(`(() => { const e = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)} || x.getAttribute('aria-label') === ${JSON.stringify(label)}); if (!e || e.disabled) return false; e.click(); return true; })()`);
const clickId = (id) => ev(`(() => { const e = document.querySelector('[data-testid="${id}"]'); if (!e || e.disabled) return false; e.click(); return true; })()`);
const text = (id) => `(document.querySelector('[data-testid="${id}"]')?.textContent ?? '').trim()`;
const setSelect = (sel, value) => ev(`(() => { const s = document.querySelector(${JSON.stringify(sel)}); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return s.value; })()`);
const body = () => ev('document.body.innerText');
const lastBody = (re) => { let hit = null; for (const [k, v] of bodies) if (re.test(k)) hit = v; return hit; };
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
async function wsProbe(path) {   // a browser WebSocket from the REAL authenticated page: same origin, no token in the URL, cookie transport only
	return ev(`new Promise((resolve) => { const u = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + ${JSON.stringify(path)}; const w = new WebSocket(u); const r = { path: ${JSON.stringify(path)}, opened: false, frames: 0, closeCode: null }; w.onopen = () => { r.opened = true; }; w.onmessage = () => { r.frames++; }; w.onclose = (e) => { r.closeCode = e.code; resolve(r); }; setTimeout(() => { r.timeout = true; try { w.close(); } catch {} resolve(r); }, 8000); })`);
}
await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
const out = { mode: MODE, who: WHO, steps: [], api: {} };
const step = (name, data = {}) => out.steps.push({ step: name, ...data });
const t0 = Date.now();

// ---- real Clerk sign-in ----------------------------------------------------------------------------------
async function signIn() {
	await goto('/sign-in');
	await waitFor(`!!document.querySelector('input[name=identifier]')`, 60000);
	const signinText = await body();
	const info = { clerkUiRendered: true, demoButtonPresent: signinText.includes('ENTER DEMO WORKSPACE'), developmentModeBadge: /Development mode/.test(signinText) };
	await ev(`document.querySelector('input[name=identifier]').focus()`); await cdp.send('Input.insertText', { text: user.email });
	await sleep(400); await click('Continue');
	await waitFor(`!!document.querySelector('input[name=password]')`, 30000);
	await sleep(1500);
	await ev(`document.querySelector('input[name=password]').focus()`); await cdp.send('Input.insertText', { text: user.password });
	await sleep(600); await click('Continue');
	await sleep(4000);
	if ((await ev('location.href')).includes('/sign-in') && /Enter your password/.test(await body())) { await click('Continue'); }
	let usedClientTrust = false;
	const until = Date.now() + 60000;
	for (;;) {
		const href = await ev('location.href'); const t = await body();
		if (!href.includes('/sign-in')) break;
		if (href.includes('client-trust') || /Check your email|verification code/i.test(t)) {
			if (!usedClientTrust) { usedClientTrust = true; await ev(`document.querySelector('input').focus()`); for (const ch of '424242') { await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch }); await sleep(120); } }
		}
		if (Date.now() > until) throw new Error('signin timeout: ' + href.replace(/[?#].*/, '') + ' :: ' + t.replace(/\s+/g, ' ').slice(0, 300));
		await sleep(400);
	}
	info.clientTrustVerificationUsed = usedClientTrust;     // Clerk's documented test verification code for +clerk_test addresses (424242); no bypass
	info.postSigninLanding = new URL(await ev('location.href')).pathname;
	return info;
}
const cookieNames = () => ev(`document.cookie.split(';').map((c) => c.trim().split('=')[0])`);
const storageScan = () => ev(`(async () => { const jwt = /eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\./; const scan = (s) => { let hit = false; const keys = []; for (let i = 0; i < s.length; i++) { const k = s.key(i); keys.push(k); if (jwt.test(s.getItem(k) ?? '')) hit = true; } return { keys: keys.length, jwtLike: hit }; };
  const idb = []; try { const dbs = await indexedDB.databases(); for (const d of dbs) idb.push(d.name); } catch {}
  let idbJwt = false; for (const name of idb) { try { await new Promise((resolve) => { const r = indexedDB.open(name); r.onsuccess = () => { const db = r.result; const stores = [...db.objectStoreNames]; let pending = stores.length; if (!pending) { db.close(); resolve(); return; } for (const sn of stores) { const g = db.transaction(sn).objectStore(sn).getAll(); g.onsuccess = () => { try { if (jwt.test(JSON.stringify(g.result))) idbJwt = true; } catch {} if (--pending === 0) { db.close(); resolve(); } }; g.onerror = () => { if (--pending === 0) { db.close(); resolve(); } }; } }; r.onerror = () => resolve(); }); } catch {} }
  return { localStorage: scan(localStorage), sessionStorage: scan(sessionStorage), indexedDB: { databases: idb.length, jwtLike: idbJwt } }; })()`);

const signin = await signIn();
if (MODE === 'wrong-party') {   // backend configured with a DIFFERENT authorized party: the real Clerk session must be REJECTED (no loosening, no demo fallback)
	await goto('/app'); await sleep(8000);
	const meR = rest.filter((r) => /\/product\/v1\/me$/.test(r.url));
	out.steps.push({ step: 'wrong-party', clerkSignInCompleted: true, me_statuses: meR.map((r) => r.status), identityChipVisible: await ev(`!!document.querySelector('[data-testid="identity-chip"]')`), landedPath: await ev('location.pathname'), demoFallback: (await body()).includes('ENTER DEMO WORKSPACE') });
	writeFileSync(OUT, JSON.stringify(out, null, 1)); await cdp.send('Browser.close').catch(() => {}); process.exit(0);
}
await goto('/app');
await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000);
const idChip = await ev(text('identity-chip'));
await sleep(800);
const meRec = lastBody(/GET \/product\/v1\/me$/), sysRec = lastBody(/GET \/product\/v1\/system$/);
step('signin', { ...signin, appReached: true, identityChipShowsProvider: /CLERK/i.test(idChip), identityChipShowsDemo: /DEMO/i.test(idChip), cookieNames: (await cookieNames()).filter((n) => /^(__session|__client_uat)/.test(n)), clerkGlobal: await ev(`typeof window.Clerk !== 'undefined'`) });
step('identity', { system: sysRec && { status: sysRec.status, auth_provider: sysRec.body?.auth_provider, demo_mode: sysRec.body?.demo_mode, model_id: sysRec.body?.model_id, software_system: sysRec.body?.software_system, product_api_implementation: sysRec.body?.product_api_implementation, hardware_mode: sysRec.body?.hardware_mode, physical_hardware_available: sysRec.body?.physical_hardware_available, federation_runtime: sysRec.body?.federation_runtime },
	me: meRec && { status: meRec.status, auth_provider: meRec.body?.auth_provider, demo_mode: meRec.body?.demo_mode, user_id_is_clerk_shaped: /^user_/.test(meRec.body?.user_id ?? ''), user_id_is_demo: /^demo:/.test(meRec.body?.user_id ?? ''), user_id_label: user.label } });
step('rest-bearer', { restCalls: rest.filter((r) => r.method === 'GET').slice(0, 6).map((r) => ({ path: new URL(r.url).pathname, status: r.status, bearer_present: r.bearer ?? null, bearer_jwt_shaped: r.bearerJwtShape ?? null })), token_value_recorded: false });
await shot('app_after_signin');

let sessionId = KNOWN_SESSION, runId = KNOWN_RUN;
if (MODE === 'a-journey') {
	await click('Device'); await waitFor(`location.pathname === '/app/device'`);
	await waitFor(`!!document.querySelector('#scenario')`);
	await setSelect('#scenario', 'MIXED_MONITORING_SESSION');
	await click('ATTACH NHM VIRTUAL WEARABLE');
	await waitFor(`!!document.querySelector('[data-testid="device-state"]')`);
	await click('SCAN'); await waitFor(`${text('device-state')} === 'FOUND'`);
	await click('PAIR / CONNECT'); await waitFor(`${text('device-state')} === 'CONNECTED'`);
	step('device', { state: 'CONNECTED', simulatedVisible: (await body()).includes('SIMULATED') });
	await click('Monitor'); await waitFor(`location.pathname === '/app/monitoring'`);
	await clickId('create-session'); await waitFor(`${text('session-state')} === 'DEVICE_READY'`);
	sessionId = await ev(text('session-id'));
	await waitFor(`${text('stream-status')}.includes('OPEN')`, 30000);
	await clickId('start-session');
	const seen = { monitoring: new Set(), models: new Set(), cals: new Set(), device: new Set(), gap: false };
	const until = Date.now() + 360000;
	for (;;) {
		const s = await ev(`(() => { const q = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim(); return { dev: q('live-device-state'), mon: q('monitoring-state'), gap: q('gap-list'), model: q('inf-model'), cal: q('inf-cal'), done: !!document.querySelector('[data-testid="session-complete"]'), err: !!document.querySelector('[data-testid="stream-error"]') }; })()`);
		if (s.mon) seen.monitoring.add(s.mon); if (s.model) seen.models.add(s.model); if (s.cal) seen.cals.add(s.cal); if (s.dev) seen.device.add(s.dev); if (/\[\d+, \d+\]/.test(s.gap)) seen.gap = true;
		if (s.err) throw new Error('monitoring stream error');
		if (s.done) break;
		if (Date.now() > until) throw new Error('monitoring timeout');
		await sleep(80);
	}
	const monSocket = [...sockets.values()].find((s) => /\/sessions\/[^/]+\/live$/.test(s.pathname));
	step('monitoring', { finalState: await ev(text('session-state')), complete: true, models: [...seen.models], calibrations: [...seen.cals], deviceStatesSeen: [...seen.device], monitoringStatesSeen: [...seen.monitoring], gapSeen: seen.gap, websocket: monSocket && { ...monSocket, sessionIdInPathIsOwned: monSocket.pathname.includes(sessionId) } });
	await shot('monitoring_done');
	// history
	await click('History'); await waitFor(`location.pathname === '/app/history'`);
	await waitFor(`!!document.querySelector('[data-testid="session-table"]')`);
	const listed = await ev(`[...document.querySelectorAll('[data-testid="session-table"] tbody tr')].some((r) => r.textContent.includes(${JSON.stringify(sessionId)}))`);
	await goto(`/app/history/${encodeURIComponent(sessionId)}`);
	await waitFor(`document.body.innerText.includes('Persisted session summary') && document.body.innerText.includes('Bounded decimated ECG preview')`, 60000);
	const sum = lastBody(/GET \/product\/v1\/sessions\/[^/]+\/summary$/), tl = lastBody(/GET \/product\/v1\/sessions\/[^/]+\/timeline$/);
	step('history', { listed, summaryStatus: sum?.status, timelineStatus: tl?.status, previews: tl?.body?.waveform_previews?.length ?? 0, completed: sum?.body?.session_state ?? sum?.body?.state ?? null });
	// federation
	await click('Federation'); await waitFor(`location.pathname === '/app/federation'`);
	await waitFor(`document.body.innerText.includes('8 logical clients ready')`, 240000);
	const fedRest = rest.filter((r) => /\/federation/.test(r.url)).map((r) => ({ path: new URL(r.url).pathname, status: r.status, bearer_present: r.bearer ?? null }));
	await setSelect('[data-testid="cfg-run-type"]', 'LIVE_RUN'); await setSelect('[data-testid="cfg-algorithm"]', 'FEDAVG'); await setSelect('[data-testid="cfg-mode"]', 'SECAGG_SHADOW');
	await clickId('cfg-submit');
	await waitFor(`location.pathname === '/app/federation/live' && ${text('run-status')}.length > 0`, 60000);
	runId = new URL(ORIGIN + await ev('location.pathname + location.search')).searchParams.get('run');
	let verified = false, plain = false; const until2 = Date.now() + 900000; let maxSub = 0;
	for (;;) {
		const s = await ev(`(() => { const q = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim(); const states = [...document.querySelectorAll('[data-testid="client-grid"] [data-state]')].map((e) => e.getAttribute('data-state')); return { status: q('run-status'), updates: q('update-ready-count'), secagg: q('secagg-status'), agg: q('authoritative-aggregate'), sub: states.filter((x) => x === 'SUBMITTED').length, candidate: q('candidate-live'), err: !!document.querySelector('[data-testid="stream-error"]') }; })()`);
		maxSub = Math.max(maxSub, s.sub); if (s.secagg.includes('SHADOW_VERIFIED')) verified = true; if (s.agg.endsWith('PLAIN')) plain = true;
		if (s.err) throw new Error('federation stream error');
		if (s.status.includes('COMPLETED') || s.status.includes('FAILED')) { out.fedFinal = s; break; }
		if (Date.now() > until2) throw new Error('federation timeout');
		await sleep(150);
	}
	const fedSocket = [...sockets.values()].find((s) => /\/federation\/runs\/[^/]+\/live$/.test(s.pathname));
	step('federation', { runStatusText: out.fedFinal.status, updatesText: out.fedFinal.updates, maxClientsSubmittedAtOnce: maxSub, secaggShadowVerifiedSeen: verified, aggregationPlainSeen: plain, preRunRest: fedRest.slice(0, 8), websocket: fedSocket && { ...fedSocket, runIdInPathIsOwned: fedSocket.pathname.includes(runId) } });
	await shot('federation_done');
	const runRec = lastBody(/GET \/product\/v1\/federation\/runs\/[^/]+$/);
	await goto(`/app/federation/rounds?run=${encodeURIComponent(runId)}`); await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000);
	const rr = lastBody(/GET \/product\/v1\/federation\/runs\/[^/]+$/), rounds = lastBody(/GET \/product\/v1\/federation\/runs\/[^/]+\/rounds$/);
	step('federation-run-rest', { status: rr?.status, run_status: rr?.body?.status, run_type: rr?.body?.run_type, algorithm: rr?.body?.algorithm, secagg_mode: rr?.body?.secagg_mode, base_model_id: rr?.body?.base_model_id, client_count: rr?.body?.client_ids?.length ?? rr?.body?.config?.client_ids?.length ?? null, planned_rounds: rr?.body?.planned_rounds ?? rr?.body?.config?.planned_rounds ?? null, candidate_count: rr?.body?.candidate_ids?.length ?? null,
		rounds_status: rounds?.status, round_states: rounds?.body?.map?.((r) => r.state) ?? null, accepted_updates: rounds?.body?.map?.((r) => r.accepted_update_count) ?? null });
	// models / research / system
	await click('Models'); await waitFor(`location.pathname === '/app/models' && !!document.querySelector('[data-testid="candidate-card"]')`, 60000);
	const mod = lastBody(/GET \/product\/v1\/models$/);
	step('models', { candidates: await ev(`document.querySelectorAll('[data-testid="candidate-card"]').length`), productionDeployed: await ev(`[...document.querySelectorAll('[data-testid="production-deployed"]')].map((e) => e.textContent.trim())`), released_default: mod?.body?.released_default_model_id, controls: await ev(`[...document.querySelectorAll('button,a')].map((b) => b.textContent.trim()).filter((t) => /deploy|promote|default|switch|inference|use candidate/i.test(t))`), candidate: mod?.body?.capstone_fl_candidates?.map((c) => ({ candidate_id: c.candidate_id, state_digest: c.state_digest, governance_status: c.governance_status, sandbox_status: c.sandbox_status, production_deployed: c.production_deployed, validation_status: c.validation_status, parent_model_id: c.parent_model_id })) });
	await goto('/app/research/ml'); await waitFor(`document.body.innerText.includes('MODEL_V2_NOT_PROMOTED_RELEASE_CI') && document.body.innerText.includes('SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED')`, 60000);
	const ml = lastBody(/GET \/product\/v1\/research\/ml$/); step('research-ml', { status: ml?.status, promotionDistinction: true });
	await goto('/app/research/fl'); await waitFor(`document.body.innerText.includes('V2-FL-004') && document.body.innerText.includes('V2-FL-005')`, 60000);
	const fl = lastBody(/GET \/product\/v1\/research\/fl$/); step('research-fl', { status: fl?.status, engineeringSeparate: (await body()).includes('V2-FL-005 is not scientific efficacy') });
	await goto('/app/system'); await waitFor(`document.body.innerText.includes('hardware_mode')`, 30000); step('system-page', { simulatedOnly: (await body()).includes('SIMULATED_ONLY') });
	// refresh restores the Clerk session (no local token persistence by NHM)
	await goto('/app'); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000);
	const reMe = lastBody(/GET \/product\/v1\/me$/);
	step('refresh', { identityRestored: true, me_status: reMe?.status, auth_provider: reMe?.body?.auth_provider, same_user_id: reMe?.body?.user_id === meRec?.body?.user_id });
	out.storage = await storageScan();
	// logout
	await click('Sign out');
	await waitFor(`location.pathname === '/sign-in'`, 30000); await sleep(2500);
	const post = await body();
	await goto('/app');
	for (let i = 0; i < 100 && !(await ev("location.pathname.startsWith('/sign-in')")); i++) await sleep(150);
	const landed = await ev('location.pathname');
	const cookiesAfter = (await cookieNames()).filter((n) => /^__session$/.test(n));
	step('logout', { redirectedToSignIn: post.includes('Sign in to NHM') || landed === '/sign-in', appRedirectsToSignIn: landed.startsWith('/sign-in'), identityChipVisibleAfter: await ev(`!!document.querySelector('[data-testid="identity-chip"]')`), sessionCookiePresentAfter: cookiesAfter.length > 0, demoFallback: (await body()).includes('ENTER DEMO WORKSPACE') });
	const wsAfter = await wsProbe(`/product/v1/sessions/${sessionId}/live`);
	step('logout-websocket', { ...wsAfter, expected: 4401 });
	const monAfterRest = await ev(`fetch('/product/v1/sessions/${sessionId}', { credentials: 'include' }).then((r) => r.status)`);
	step('logout-rest-no-token', { status: monAfterRest });
}
if (MODE === 'b-isolation') {
	// B owns nothing of A's. 1) UI navigation to A's resources (B's real token, app's own requests). 2) probes rewriting one app request to A-owned targets/controls. 3) browser WebSockets to A's live streams.
	await goto(`/app/history/${encodeURIComponent(sessionId)}`); await sleep(6000);
	const ui = ['summary', 'timeline', ''].map((suffix) => { const rec = lastBody(new RegExp(`GET /product/v1/sessions/${sessionId}${suffix ? '/' + suffix : ''}$`)); return { target: suffix || 'session', status: rec?.status ?? null }; });
	step('b-rest-ui', { results: ui });
	const targets = [['GET', `/product/v1/sessions/${sessionId}`, null, 'read A session'], ['GET', `/product/v1/sessions/${sessionId}/summary`, null, 'read A summary'], ['GET', `/product/v1/sessions/${sessionId}/timeline`, null, 'read A timeline'],
		['GET', `/product/v1/federation/runs/${runId}`, null, 'read A run'], ['GET', `/product/v1/federation/runs/${runId}/rounds`, null, 'read A rounds'], ['POST', `/product/v1/federation/runs/${runId}/start`, '{}', 'start A run (control)'], ['POST', `/product/v1/sessions/${sessionId}/start`, '{}', 'start A monitoring session (control)'], ['POST', `/product/v1/sessions/${sessionId}/stop`, '{}', 'stop A monitoring session (control)'],
		['GET', '/product/v1/sessions/SESS-NHM-DOES-NOT-EXIST', null, 'CONTROL: nonexistent session (must be 404, proving the rewrite reaches the target and 403 is ownership)'], ['GET', '/product/v1/research/ml', null, 'CONTROL: global research view (must be 200)']];
	for (const [method, path, post, label] of targets) {
		const q = { method, to: path, postData: post, done: false, label, match: (req) => req.url.includes('/product/v1/devices') && req.method === 'GET' };
		probeQueue = [q]; probes.push(q);
		await goto('/app/device'); await waitFor(`!!document.querySelector('#scenario')`, 30000); await sleep(1500);
		if (!q.done) { await click('Device'); await sleep(1500); }
		const rec = rest.filter((r) => r.url.endsWith(path)).slice(-1)[0];
		q.status = q.status ?? rec?.status ?? null; q.bearerKept = q.bearerKept ?? null;
	}
	probeQueue = [];
	step('b-rest-probes', { results: probes.map((q) => ({ label: q.label, method: q.method, rewritten: !!q.done, status: q.status, response_path: q.responseUrl ?? null, app_bearer_kept: q.bearerKept })) });
	step('b-websockets', { monitoring: await wsProbe(`/product/v1/sessions/${sessionId}/live`), federation: await wsProbe(`/product/v1/federation/runs/${runId}/live`) });
	// B's own global (non-owner-scoped) views stay available
	await goto('/app/research/ml'); await waitFor(`document.body.innerText.includes('MODEL_V2_NOT_PROMOTED_RELEASE_CI')`, 60000);
	step('b-global-read', { research_ml_status: lastBody(/GET \/product\/v1\/research\/ml$/)?.status });
	await goto('/app/history'); await sleep(3000);
	const mine = lastBody(/GET \/product\/v1\/sessions$/);
	step('b-own-list', { status: mine?.status, count: Array.isArray(mine?.body) ? mine.body.length : null, contains_a_session: JSON.stringify(mine?.body ?? '').includes(sessionId) });
	out.storage = await storageScan();
}
if (MODE === 'a-return') {
	await goto('/app/history'); await waitFor(`!!document.querySelector('[data-testid="session-table"]')`, 60000);
	const listed = await ev(`[...document.querySelectorAll('[data-testid="session-table"] tbody tr')].some((r) => r.textContent.includes(${JSON.stringify(sessionId)}))`);
	await goto(`/app/history/${encodeURIComponent(sessionId)}`);
	await waitFor(`document.body.innerText.includes('Persisted session summary')`, 60000);
	const sum = lastBody(/GET \/product\/v1\/sessions\/[^/]+\/summary$/), tl = lastBody(/GET \/product\/v1\/sessions\/[^/]+\/timeline$/);
	step('return-history', { listed, summaryStatus: sum?.status, timelineStatus: tl?.status, summary_digest: JSON.stringify(sum?.body ?? null).length, previews: tl?.body?.waveform_previews?.length ?? 0 });
	await goto(`/app/federation/rounds?run=${encodeURIComponent(runId)}`); await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000);
	const run = lastBody(/GET \/product\/v1\/federation\/runs\/[^/]+$/);
	step('return-federation', { roundCards: await ev(`document.querySelectorAll('[data-testid="round-cards"] li').length`), run_status: run?.body?.status, run_type: run?.body?.run_type });
	await click('Models'); await waitFor(`location.pathname === '/app/models' && !!document.querySelector('[data-testid="candidate-card"]')`, 60000);
	const mod = lastBody(/GET \/product\/v1\/models$/);
	step('return-models', { candidates: mod?.body?.capstone_fl_candidates?.map((c) => ({ governance_status: c.governance_status, sandbox_status: c.sandbox_status, production_deployed: c.production_deployed })), released_default: mod?.body?.released_default_model_id });
	out.api.same_user_id = { me_user_id_hash_len: (meRec?.body?.user_id ?? '').length };
}
out.sessionId = sessionId; out.runId = runId; out.userIdForOwnershipCheck = meRec?.body?.user_id ?? null;
out.network = { hosts: [...hosts].sort(), clerkOwnedHosts: [...hosts].filter((h) => /clerk\.(accounts\.dev|com)|clerk-telemetry\.com$/.test(h)).sort(), allRestHaveBearer: rest.filter((r) => r.status !== undefined).every((r) => r.bearer !== false || /\/system$/.test(r.url)), websockets: [...sockets.values()] };
out.console_errors = errors.filter((e) => !/Failed to load resource|clerk-telemetry|ERR_/i.test(e)); out.console_errors_raw_count = errors.length;
out.elapsed_s = Math.round((Date.now() - t0) / 1000);
writeFileSync(OUT, JSON.stringify(out, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
