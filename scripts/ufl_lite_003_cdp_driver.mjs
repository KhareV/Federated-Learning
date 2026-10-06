// UFL-LITE-003 real-browser driver (REAL headless Chrome via CDP; REAL Clerk TEST sign-in, or the offline DemoAuth journey for the negative check).
// Observes the APP's own requests/events; records only booleans, statuses, counts and digests (never tokens, cookies, emails or passwords).
//   node scripts/ufl_lite_003_cdp_driver.mjs <mode> <debugPort> <origin> <usersJson> <A|B> <outJson> <shotDir> [liveRunId]
//   modes: owner-live | b-isolation | a-return
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const [, , MODE, debugPort, ORIGIN, USERS, WHO, OUT, SHOTS, KNOWN_RUN] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const user = JSON.parse(readFileSync(USERS))[WHO];
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
const hosts = new Set(), errors = [], rest = [], sockets = new Map(), reqIds = new Map(), bodies = new Map(), events = new Map(), probes = [];
let probeQueue = [];
const redact = (u) => u.replace(/([?&](token|__session|jwt|access_token)=)[^&]+/gi, '$1<REDACTED>');
cdp.on((m, p) => {
	if (m === 'Network.requestWillBeSent') { try { hosts.add(new URL(p.request.url).host); } catch { /* data: */ } reqIds.set(p.requestId, { url: p.request.url, method: p.request.method }); }
	if (m === 'Network.requestWillBeSentExtraInfo') { const r = reqIds.get(p.requestId); if (r) { const h = Object.fromEntries(Object.entries(p.headers).map(([k, v]) => [k.toLowerCase(), v])); r.bearer = /^Bearer\s+\S{20,}/.test(h.authorization ?? ''); } }
	if (m === 'Network.responseReceived') {
		for (const q of probes) if (q.networkId && q.networkId === p.requestId) q.status = p.response.status;
		const r = reqIds.get(p.requestId);
		if (r) { r.status = p.response.status; r.url = p.response.url; if (new URL(r.url).pathname.startsWith('/product/v1/')) rest.push(r); }
	}
	if (m === 'Network.loadingFinished') { const r = reqIds.get(p.requestId); if (r && r.url.includes('/product/v1/')) void cdp.send('Network.getResponseBody', { requestId: p.requestId }).then((b) => { const k = `${r.method} ${new URL(r.url).pathname}`; try { bodies.set(k, { status: r.status, body: JSON.parse(b.body) }); } catch { bodies.set(k, { status: r.status, body: null }); } }).catch(() => {}); }
	if (m === 'Network.webSocketCreated') sockets.set(p.requestId, { pathname: new URL(p.url.replace(/^ws/, 'http')).pathname, urlHasToken: /[?&](token|__session|jwt|access_token)=|eyJ/i.test(p.url), handshakeStatus: null, framesReceived: 0, cookieSessionSent: null });
	if (m === 'Network.webSocketWillSendHandshakeRequest') { const s = sockets.get(p.requestId); if (s) s.cookieSessionSent = /(^|;\s*)__session=/.test(Object.fromEntries(Object.entries(p.request.headers).map(([k, v]) => [k.toLowerCase(), v])).cookie ?? ''); }
	if (m === 'Network.webSocketHandshakeResponseReceived') { const s = sockets.get(p.requestId); if (s) s.handshakeStatus = p.response.status; }
	if (m === 'Network.webSocketFrameReceived') {
		const s = sockets.get(p.requestId);
		if (s) { s.framesReceived++; try { const e = JSON.parse(p.response.payloadData); if (e.event_id && e.run_id) events.set(e.event_id, e); } catch { /* non-JSON */ } }
	}
	if (m === 'Fetch.requestPaused') {
		const q = probeQueue.find((x) => !x.done && x.match(p.request));
		if (q) { q.done = true; q.networkId = p.networkId ?? p.requestId; q.bearerKept = /^Bearer\s+\S{20,}/.test(p.request.headers.Authorization ?? p.request.headers.authorization ?? ''); void cdp.send('Fetch.continueRequest', { requestId: p.requestId, url: new URL(q.to, ORIGIN).toString(), method: q.method, ...(q.postData ? { postData: Buffer.from(q.postData).toString('base64') } : {}) }).catch((e) => errors.push(`PROBE:${e}`)); }
		else void cdp.send('Fetch.continueRequest', { requestId: p.requestId }).catch(() => {});
	}
	if (m === 'Runtime.exceptionThrown') errors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200));
});
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
if (MODE === 'b-isolation') await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/product/v1/*', requestStage: 'Request' }] });
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(`eval: ${expression.slice(0, 80)} :: ${JSON.stringify(r.exceptionDetails).slice(0, 200)}`); return r.result.value; }
async function waitFor(expression, timeout = 120000) { const until = Date.now() + timeout; while (Date.now() < until) { let v = null; try { v = await ev(expression); } catch { /* navigating */ } if (v) return v; await sleep(100); } throw new Error(`timeout: ${expression.slice(0, 120)}`); }
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(300); };
const click = (label) => ev(`(() => { const e = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)} || x.getAttribute('aria-label') === ${JSON.stringify(label)}); if (!e || e.disabled) return false; e.click(); return true; })()`);
const clickId = (id) => ev(`(() => { const e = document.querySelector('[data-testid="${id}"]'); if (!e || e.disabled) return false; e.click(); return true; })()`);
const setSelect = (sel, value) => ev(`(() => { const s = document.querySelector(${JSON.stringify(sel)}); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return s.value; })()`);
const body = () => ev('document.body.innerText');
const lastBody = (re) => { let hit = null; for (const [k, v] of bodies) if (re.test(k)) hit = v; return hit; };
async function wsProbe(path) { return ev(`new Promise((resolve) => { const u = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + ${JSON.stringify(path)}; const w = new WebSocket(u); const r = { path: ${JSON.stringify(path)}, opened: false, frames: 0, closeCode: null }; w.onopen = () => { r.opened = true; }; w.onmessage = () => { r.frames++; }; w.onclose = (e) => { r.closeCode = e.code; resolve(r); }; setTimeout(() => { r.timeout = true; try { w.close(); } catch {} resolve(r); }, 8000); })`); }
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
const out = { mode: MODE, who: WHO, steps: [] };
const step = (name, data = {}) => out.steps.push({ step: name, ...data });
const t0 = Date.now();

const FACTS = `(() => { const q = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim().replace(/\\s+/g, ' '); const cards = [...document.querySelectorAll('[data-client]')]; const owner = document.querySelector('[data-role="AUTHENTICATED_OWNER"]'); const text = document.body.innerText;
 return { clientIds: cards.map((c) => c.getAttribute('data-client')), ownerCards: document.querySelectorAll('[data-role="AUTHENTICATED_OWNER"]').length, peerCards: document.querySelectorAll('[data-role="SYNTHETIC_PEER"]').length, ownerClient: owner?.getAttribute('data-client') ?? null, ownerRole: owner?.getAttribute('data-role') ?? null, ownerState: owner?.getAttribute('data-state') ?? null,
 ownerText: (owner?.textContent ?? '').replace(/\\s+/g, ' ').slice(0, 500), myParticipation: q('my-participation').slice(0, 900), myExamples: q('my-local-examples'), myRounds: q('my-completed-rounds'), myUpdates: q('my-updates-produced'), rawSent: q('my-raw-examples-sent'), participantsNote: q('participants-note'),
 runStatus: q('run-status'), updateReady: q('update-ready-count'), streamError: !!document.querySelector('[data-testid="stream-error"]'), replayNote: !!document.querySelector('[data-testid="replay-note"]'), federatedParticipantsTitle: text.includes('Federated participants'), eightLogicalTitle: text.includes('Eight logical clients'),
 myEdgeMentions: (text.match(/MY EDGE CLIENT/g) || []).length, authenticatedOwnerMentions: (text.match(/AUTHENTICATED OWNER/g) || []).length, syntheticPeerMentions: (text.match(/SYNTHETIC PEER/g) || []).length, forbiddenWords: (text.match(/contribution|influence score|personali[sz]ed|personal model|my ECG|my monitoring|opt[- ]in|consent|join federation/ig) || []), interactiveConsentControls: document.querySelectorAll('input[type=checkbox],[role=switch]').length, updatesSubmittedLabelForOwner: /updates submitted/i.test(q('my-participation')) }; })()`;

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
		if (Date.now() > until) throw new Error('signin timeout');
		await sleep(400);
	}
	await goto('/app'); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000); await sleep(800);
	const sys = lastBody(/GET \/product\/v1\/system$/), me = lastBody(/GET \/product\/v1\/me$/);
	step('signin', { clientTrustVerificationUsed: trust, system: { auth_provider: sys?.body?.auth_provider, demo_mode: sys?.body?.demo_mode, model_id: sys?.body?.model_id }, me: { status: me?.status, auth_provider: me?.body?.auth_provider, demo_mode: me?.body?.demo_mode, user_id_is_clerk_shaped: /^user_/.test(me?.body?.user_id ?? ''), user_id_is_demo: /^demo:/.test(me?.body?.user_id ?? '') }, clerkGlobal: await ev(`typeof window.Clerk !== 'undefined'`) });
}
async function startRun(runType, algorithm, mode) {
	await goto('/app/federation'); await waitFor(`document.body.innerText.includes('8 logical clients ready')`, 240000);
	const clients = lastBody(/GET \/product\/v1\/federation\/clients$/);
	await setSelect('[data-testid="cfg-run-type"]', runType); await setSelect('[data-testid="cfg-algorithm"]', algorithm); await setSelect('[data-testid="cfg-mode"]', mode);
	await clickId('cfg-submit');
	await waitFor(`location.pathname === '/app/federation/live' && ${`(document.querySelector('[data-testid="run-status"]')?.textContent ?? '')`}.length > 0`, 60000);
	const runId = new URL(ORIGIN + await ev('location.pathname + location.search')).searchParams.get('run');
	return { runId, clients };
}
const waitDone = async (timeout = 900000) => { const until = Date.now() + timeout; for (;;) { const f = await ev(FACTS); if (f.streamError) throw new Error('federation stream error'); if (f.runStatus.includes('COMPLETED') || f.runStatus.includes('FAILED')) return f; if (Date.now() > until) throw new Error('federation timeout'); await sleep(150); } };
function authoritative(runId) {
	const evs = [...events.values()].filter((e) => e.run_id === runId).sort((a, b) => a.sequence_index - b.sequence_index);
	const updates = {}, states = {}; let cand = null, count = 0, sequenceOk = true;
	evs.forEach((e, i) => { if (e.sequence_index !== i) sequenceOk = false; });
	for (const e of evs) {
		if (e.event_type === 'client.update_ready') { updates[e.payload.round_id] ??= {}; updates[e.payload.round_id][e.payload.client_id] = { update_sha256: e.payload.update_digest, examples_seen: e.payload.examples_seen }; count++; }
		if (e.event_type === 'aggregation.status') states[e.payload.round_id] = e.payload.state_digest;
		if (e.event_type === 'candidate.created') cand = e.payload.state_digest;
	}
	const run = lastBody(new RegExp(`GET /product/v1/federation/runs/${runId}$`)), rounds = lastBody(new RegExp(`GET /product/v1/federation/runs/${runId}/rounds$`));
	return { event_count: evs.length, sequence_contiguous: sequenceOk, update_ready_events: count, update_digests: updates, round_state_digests: states, candidate_state_digest_event: cand, run: run && { status: run.body?.status, run_type: run.body?.run_type, algorithm: run.body?.algorithm, secagg_mode: run.body?.secagg_mode, client_ids: run.body?.client_ids, planned_rounds: run.body?.planned_rounds, candidate_ids: run.body?.candidate_ids }, rounds: rounds && { status: rounds.status, accepted: rounds.body?.map?.((r) => r.accepted_update_count), states: rounds.body?.map?.((r) => r.state) } };
}
const wsSummary = () => [...sockets.values()].map((s) => ({ pathname: s.pathname, handshakeStatus: s.handshakeStatus, urlHasToken: s.urlHasToken, cookieSessionSent: s.cookieSessionSent, framesReceived: s.framesReceived }));
const modelsFacts = () => { const m = lastBody(/GET \/product\/v1\/models$/); return m && { status: m.status, released_default: m.body?.released_default_model_id, candidates: m.body?.capstone_fl_candidates?.map((c) => ({ candidate_id: c.candidate_id, state_digest: c.state_digest, governance_status: c.governance_status, sandbox_status: c.sandbox_status, production_deployed: c.production_deployed, parent_model_id: c.parent_model_id })) }; };

await clerkSignIn();

if (MODE === 'owner-live') {
	const { runId, clients } = await startRun('LIVE_RUN', 'FEDAVG', 'SECAGG_SHADOW');
	step('clients-rest', { status: clients?.status, count: clients?.body?.length, site00: clients?.body?.find?.((c) => c.client_id === 'SIM_FL_SITE_00') && { local_example_count: clients.body.find((c) => c.client_id === 'SIM_FL_SITE_00').local_example_count, edge_node_id: clients.body.find((c) => c.client_id === 'SIM_FL_SITE_00').edge_node_id }, ids: clients?.body?.map?.((c) => c.client_id) });
	// refresh mid-run (after the first round's updates exist)
	await waitFor(`Number((document.querySelector('[data-testid="update-ready-count"]')?.textContent ?? '0').trim()) >= 8`, 600000);
	const before = await ev(FACTS);
	await cdp.send('Page.reload'); await sleep(500);
	await waitFor(`!!document.querySelector('[data-testid="client-grid"]')`, 60000);
	await waitFor(`Number((document.querySelector('[data-testid="update-ready-count"]')?.textContent ?? '0').trim()) >= 1`, 60000);
	const after = await ev(FACTS);
	step('refresh-mid-run', { before_ownerCards: before.ownerCards, after_ownerCards: after.ownerCards, after_peerCards: after.peerCards, after_ownerClient: after.ownerClient, after_clientIds: after.clientIds, after_streamError: after.streamError, update_ready_before: before.updateReady, update_ready_after: after.updateReady, sockets_after_refresh: wsSummary().length });
	const done = await waitDone();
	await shot('live_completed');
	step('live-completed', done);
	step('live-authoritative', authoritative(runId));
	await goto(`/app/federation/rounds?run=${encodeURIComponent(runId)}`); await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000);
	step('rounds-page', { ownerNote: await ev(`(document.querySelector('[data-testid="rounds-owner-note"]')?.textContent ?? '').trim()`), myEdgeMentions: ((await body()).match(/MY EDGE CLIENT/g) || []).length });
	await goto('/app/models'); await waitFor(`!!document.querySelector('[data-testid="candidate-card"]')`, 60000);
	step('models-after-live', modelsFacts());
	await goto('/app/federation/clients'); await waitFor(`document.body.innerText.includes('SIM_FL_SITE_07')`, 120000); await sleep(800);
	const g = await body();
	step('global-clients-view', { clientIdsShown: ['0', '1', '2', '3', '4', '5', '6', '7'].map((i) => `SIM_FL_SITE_0${i}`).filter((id) => g.includes(id)).length, myEdgeMentions: (g.match(/MY EDGE CLIENT/g) || []).length, authenticatedOwnerMentions: (g.match(/AUTHENTICATED OWNER/gi) || []).length, syntheticPeerMentions: (g.match(/SYNTHETIC PEER/g) || []).length, ownerBoundMentions: (g.match(/owner-bound/gi) || []).length });
	await shot('global_clients');
	const rp = await startRun('REPLAY', 'FEDAVG', 'SECAGG_SHADOW');
	const rdone = await waitDone();
	await shot('replay_completed');
	step('replay', { runId_differs_from_live: rp.runId !== runId, facts: rdone, authoritative: authoritative(rp.runId) });
	await goto('/app/models'); await waitFor(`!!document.querySelector('[data-testid="candidate-card"]')`, 60000);
	step('models-after-replay', modelsFacts());
	out.liveRunId = runId; out.replayRunId = rp.runId;
}
if (MODE === 'a-return') {
	await goto(`/app/federation/live?run=${encodeURIComponent(KNOWN_RUN)}`); await waitFor(`!!document.querySelector('[data-testid="client-grid"]')`, 120000);
	await waitFor(`Number((document.querySelector('[data-testid="update-ready-count"]')?.textContent ?? '0').trim()) >= 24`, 300000);
	const done = await waitDone(300000);
	step('live-reconstructed', done);
	step('live-authoritative', authoritative(KNOWN_RUN));
	await goto(`/app/federation/rounds?run=${encodeURIComponent(KNOWN_RUN)}`); await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000);
	step('rounds-page', { ownerNote: await ev(`(document.querySelector('[data-testid="rounds-owner-note"]')?.textContent ?? '').trim()`) });
	await goto('/app/models'); await waitFor(`!!document.querySelector('[data-testid="candidate-card"]')`, 60000);
	step('models-after-restart', modelsFacts());
	out.liveRunId = KNOWN_RUN;
}
if (MODE === 'b-isolation') {
	await goto('/app/federation/clients'); await waitFor(`document.body.innerText.includes('SIM_FL_SITE_07')`, 120000); await sleep(800);
	const g = await body();
	step('global-clients-view', { clientIdsShown: ['0', '1', '2', '3', '4', '5', '6', '7'].map((i) => `SIM_FL_SITE_0${i}`).filter((id) => g.includes(id)).length, myEdgeMentions: (g.match(/MY EDGE CLIENT/g) || []).length, authenticatedOwnerMentions: (g.match(/AUTHENTICATED OWNER/gi) || []).length });
	const targets = [['GET', `/product/v1/federation/runs/${KNOWN_RUN}`, null, 'read A run'], ['GET', `/product/v1/federation/runs/${KNOWN_RUN}/rounds`, null, 'read A rounds'], ['POST', `/product/v1/federation/runs/${KNOWN_RUN}/start`, '{}', 'start A run (control)'],
		['GET', '/product/v1/federation/runs/FEDRUN-NHM-DOES-NOT-EXIST', null, 'CONTROL: nonexistent run (must be 404: proves the rewrite reaches the target)'], ['GET', '/product/v1/research/ml', null, 'CONTROL: global research view (must be 200)']];
	for (const [method, path, post, label] of targets) {
		const q = { method, to: path, postData: post, done: false, label, match: (req) => req.url.includes('/product/v1/devices') && req.method === 'GET' };
		probeQueue = [q]; probes.push(q);
		await goto('/app/device'); await waitFor(`!!document.querySelector('#scenario')`, 30000); await sleep(1500);
		if (!q.done) { await click('Device'); await sleep(1500); }
		const rec = rest.filter((r) => r.url.endsWith(path)).slice(-1)[0];
		q.status = q.status ?? rec?.status ?? null;
	}
	probeQueue = [];
	step('b-rest-probes', { results: probes.map((q) => ({ label: q.label, method: q.method, rewritten: !!q.done, status: q.status ?? null, app_bearer_kept: q.bearerKept ?? null })) });
	step('b-websocket', { federation: await wsProbe(`/product/v1/federation/runs/${KNOWN_RUN}/live`) });
	await goto(`/app/federation/live?run=${encodeURIComponent(KNOWN_RUN)}`); await sleep(6000);
	const f = await ev(FACTS);
	step('b-views-a-live-page', { ownerCards: f.ownerCards, myEdgeMentions: f.myEdgeMentions, myParticipation: f.myParticipation });
	await goto('/app/federation'); await sleep(3000);
	const mine = lastBody(/GET \/product\/v1\/federation\/runs$/);
	step('b-own-runs', { status: mine?.status, count: Array.isArray(mine?.body) ? mine.body.length : null, contains_a_run: JSON.stringify(mine?.body ?? '').includes(KNOWN_RUN) });
}
out.websockets = wsSummary();
out.network = { hosts: [...hosts].sort(), clerkOwnedHosts: [...hosts].filter((h) => /clerk\.(accounts\.dev|com)|clerk-telemetry\.com$/.test(h)).sort() };
out.console_errors = errors.filter((e) => !/Failed to load resource|clerk-telemetry|ERR_/i.test(e));
out.elapsed_s = Math.round((Date.now() - t0) / 1000);
writeFileSync(OUT, JSON.stringify(out, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
