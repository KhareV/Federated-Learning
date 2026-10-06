// CAP-010 complete faculty browser journey: REAL headless Chrome (CDP) over the faculty launcher's real stack.
// Loopback-only request interception; no mock backend, no fake data.
//   node scripts/cap_010_cdp_driver.mjs <mode: full|reload> <debugPort> <frontendOrigin> <outJson> <shotDir> [sessionId runId]
import { writeFileSync, mkdirSync } from 'node:fs';

const [, , MODE, debugPort, ORIGIN, OUT, SHOTS, KNOWN_SESSION, KNOWN_RUN] = process.argv;
mkdirSync(SHOTS, { recursive: true });
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
const requests = [], errors = [], blocked = [], sockets = [];
cdp.on((method, p) => {
	if (method === 'Network.requestWillBeSent') requests.push(p.request.url);
	if (method === 'Network.webSocketCreated') sockets.push(p.url);
	if (method === 'Fetch.requestPaused') {
		const url = p.request.url; let allowed = false;
		try { allowed = ['127.0.0.1', 'localhost'].includes(new URL(url).hostname); } catch { allowed = /^(data|blob|about):/.test(url); }
		if (!allowed) blocked.push(url);
		void cdp.send(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest', allowed ? { requestId: p.requestId } : { requestId: p.requestId, errorReason: 'BlockedByClient' }).catch((e) => errors.push(`INTERCEPT:${e}`));
	}
	if (method === 'Runtime.exceptionThrown') errors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200));
	if (method === 'Runtime.consoleAPICalled' && p.type === 'error') errors.push(p.args.map((a) => a.value ?? a.description).join(' ').slice(0, 200));
});
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
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
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(250); };
const click = (label) => ev(`(() => { const e = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)}); if (!e || e.disabled) return false; e.click(); return true; })()`);
const clickId = (id) => ev(`(() => { const e = document.querySelector('[data-testid="${id}"]'); if (!e || e.disabled) return false; e.click(); return true; })()`);
const text = (id) => `(document.querySelector('[data-testid="${id}"]')?.textContent ?? '').trim()`;
const setSelect = (sel, value) => ev(`(() => { const s = document.querySelector(${JSON.stringify(sel)}); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return s.value; })()`);
const api = (path) => ev(`fetch(${JSON.stringify(path)}).then(async (r) => ({ status: r.status, body: await r.json() }))`);
const body = () => ev('document.body.innerText');
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
const out = { mode: MODE, steps: [], api: {} };
const step = (name, data = {}) => { out.steps.push({ step: name, ...data }); };
const t0 = Date.now();
const SAMPLE = `(() => { const q = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim(); const states = [...document.querySelectorAll('[data-testid="client-grid"] [data-state]')].map((e) => e.getAttribute('data-state')); return { status: q('run-status'), updates: q('update-ready-count'), submitted: q('submitted-count'), secagg: q('secagg-status'), agg: q('authoritative-aggregate'), rounds: [...document.querySelectorAll('[data-testid="round-states"] li')].map((e) => e.textContent.trim().slice(0, 40)), submittedClients: states.filter((s) => s === 'SUBMITTED').length, candidate: q('candidate-live'), streamError: !!document.querySelector('[data-testid="stream-error"]') }; })()`;

// ---- sign-in (OFFLINE DEMO) -----------------------------------------------------------------------
await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
const signin = await body();
step('sign-in', { offlineDemoBanner: signin.includes('NHM OFFLINE FACULTY DEMO'), notClerk: signin.includes('DEMO - NOT CLERK'), clerkGlobal: await ev(`typeof window.Clerk !== 'undefined'`) });
await click('ENTER DEMO WORKSPACE');
await waitFor(`location.pathname === '/app' && !!document.querySelector('[data-testid="demo-banner"]')`);
await waitFor(`document.body.innerText.includes('ENGINEERING RUNTIME ENABLED')`, 60000);
const overview = await body();
const initial = { sessions: (await api('/product/v1/sessions')).body.length, runs: (await api('/product/v1/federation/runs')).body.length, candidates: (await api('/product/v1/models')).body.capstone_fl_candidates.length };
step('overview', { releasedModel: overview.includes('MODEL_V2_FINAL'), federationEnabled: overview.includes('ENGINEERING RUNTIME ENABLED'), hardwareSimulated: overview.includes('SIMULATED_ONLY'), notConnected: overview.includes('PHYSICAL HARDWARE: NOT CONNECTED'), initial, identity: await ev(text('identity-chip')) });
await shot('overview');

let sessionId = KNOWN_SESSION, runId = KNOWN_RUN;
if (MODE === 'full') {
	// ---- device -> monitoring -------------------------------------------------------------------------
	await click('Device'); await waitFor(`location.pathname === '/app/device'`);
	await waitFor(`!!document.querySelector('#scenario')`);
	const scenario = await setSelect('#scenario', 'MIXED_MONITORING_SESSION');
	await click('ATTACH NHM VIRTUAL WEARABLE');
	await waitFor(`!!document.querySelector('[data-testid="device-state"]')`);
	const deviceId = await ev(text('device-id'));
	await click('SCAN'); await waitFor(`${text('device-state')} === 'FOUND'`);
	await click('PAIR / CONNECT'); await waitFor(`${text('device-state')} === 'CONNECTED'`);
	const dev = await body();
	step('device', { deviceId, scenario, scenarioShown: await ev(text('device-scenario')), simulatedVisible: dev.includes('SIMULATED ONLY') || dev.includes('SIMULATED') });
	await click('Monitor'); await waitFor(`location.pathname === '/app/monitoring'`);
	await clickId('create-session'); await waitFor(`${text('session-state')} === 'DEVICE_READY'`);
	sessionId = await ev(text('session-id'));
	await waitFor(`${text('stream-status')}.includes('OPEN')`, 30000);
	await clickId('start-session');
	const seen = { device: new Set(), monitoring: new Set(), quality: new Set(), contextUnavailable: false, gap: false, models: new Set(), cals: new Set(), simBanner: false };
	const until = Date.now() + 360000;
	for (;;) {
		const s = await ev(`(() => { const q = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim(); return { dev: q('live-device-state'), mon: q('monitoring-state'), qual: q('quality-state'), ctx: !!document.querySelector('[data-testid="context-unavailable"]'), gap: q('gap-list'), model: q('inf-model'), cal: q('inf-cal'), done: !!document.querySelector('[data-testid="session-complete"]'), err: !!document.querySelector('[data-testid="stream-error"]') }; })()`);
		if (s.dev) seen.device.add(s.dev); if (s.mon) seen.monitoring.add(s.mon); if (s.qual) seen.quality.add(s.qual); if (s.ctx) seen.contextUnavailable = true;
		if (/\[\d+, \d+\]/.test(s.gap)) seen.gap = true; if (s.model) seen.models.add(s.model); if (s.cal) seen.cals.add(s.cal);
		if (s.err) throw new Error('monitoring stream error');
		if (s.done) break;
		if (Date.now() > until) throw new Error('monitoring timeout');
		await sleep(80);
	}
	const mtext = await body();
	step('monitoring', { sessionId, finalState: await ev(text('session-state')), deviceStatesSeen: [...seen.device], monitoringStatesSeen: [...seen.monitoring], qualitySeen: [...seen.quality], contextUnavailableSeen: seen.contextUnavailable, gapSeen: seen.gap, models: [...seen.models], calibrations: [...seen.cals],
		simulationVisible: mtext.includes('SIMULATED') || mtext.includes('SIMULATION'), complete: mtext.includes('Session completed') });
	await shot('monitoring_done');
}
// ---- history ------------------------------------------------------------------------------------------
await click('History'); await waitFor(`location.pathname === '/app/history'`);
await waitFor(`!!document.querySelector('[data-testid="session-table"]')`);
const listed = await ev(`[...document.querySelectorAll('[data-testid="session-table"] tbody tr')].some((r) => r.textContent.includes(${JSON.stringify(sessionId)}))`);
const detail = `/app/history/${encodeURIComponent(sessionId)}`;
await goto(detail);
await waitFor(`document.body.innerText.includes('Persisted session summary') && document.body.innerText.includes('Bounded decimated ECG preview')`, 60000);
const ht = await body();
out.api.session = await api(`/product/v1/sessions/${encodeURIComponent(sessionId)}`);
out.api.summary = await api(`/product/v1/sessions/${encodeURIComponent(sessionId)}/summary`);
out.api.timeline = await api(`/product/v1/sessions/${encodeURIComponent(sessionId)}/timeline`);
step('history', { sessionId, listed, summaryStatus: out.api.summary.status, timelineStatus: out.api.timeline.status, previews: out.api.timeline.body.waveform_previews?.length ?? 0, countBasis: ht.includes('PERSISTED INFERENCE EVENTS'), timeDomains: ht.includes('SOURCE DOMAIN') && ht.includes('PRODUCT CLOCK'), probabilityLabel: ht.includes('RESEARCH TECHNICAL METADATA'), previewIsBounded: /bounded/i.test(ht) });
await shot('history_detail');

// ---- federation -----------------------------------------------------------------------------------------
await click('Federation'); await waitFor(`location.pathname === '/app/federation'`);
await waitFor(`document.body.innerText.includes('8 logical clients ready')`, 180000);
const fedPageText = await body();
if (MODE === 'full') {
	await setSelect('[data-testid="cfg-run-type"]', 'LIVE_RUN'); await setSelect('[data-testid="cfg-algorithm"]', 'FEDAVG'); await setSelect('[data-testid="cfg-mode"]', 'SECAGG_SHADOW');
	await clickId('cfg-submit');
	await waitFor(`location.pathname === '/app/federation/live' && ${text('run-status')}.length > 0`, 60000);
	runId = new URL(ORIGIN + await ev('location.pathname + location.search')).searchParams.get('run');
	let maxSubmitted = 0, runningSeen = false, verifiedSeen = false; const aggs = new Set(); const rounds = new Set();
	const until = Date.now() + 900000;
	for (;;) {
		const s = await ev(SAMPLE);
		maxSubmitted = Math.max(maxSubmitted, s.submittedClients);
		if (s.secagg.includes('SHADOW_RUNNING')) runningSeen = true; if (s.secagg.includes('SHADOW_VERIFIED')) verifiedSeen = true;
		if (s.agg.endsWith('PLAIN')) aggs.add('PLAIN'); for (const r of s.rounds) rounds.add(r.slice(0, 8));
		if (s.streamError) throw new Error('federation stream error');
		if (s.status.includes('COMPLETED') || s.status.includes('FAILED')) break;
		if (Date.now() > until) throw new Error('federation timeout');
		await sleep(150);
	}
	const fin = await ev(SAMPLE);
	const ft = await body();
	step('federation', { runId, final: fin, maxClientsSubmittedAtOnce: maxSubmitted, shadowRunningSeen: runningSeen, shadowVerifiedSeen: verifiedSeen, shadowSequenceText: ft.match(/SHADOW_RUNNING → SHADOW_VERIFIED/)?.[0] ?? null, aggregationSeen: [...aggs], roundsSeen: [...rounds], localityOnFederationPage: fedPageText.includes('one demonstration machine'), bannersOnFederationPage: ['ENGINEERING FEDERATION DEMO', 'SIMULATED CLIENTS', 'NOT CLINICAL', 'NOT DEPLOYED'].every((b) => fedPageText.includes(b)) });
	await shot('federation_done');
}
out.api.run = await api(`/product/v1/federation/runs/${encodeURIComponent(runId)}`);
out.api.rounds = await api(`/product/v1/federation/runs/${encodeURIComponent(runId)}/rounds`);
if (MODE === 'reload') {
	await goto(`/app/federation/rounds?run=${encodeURIComponent(runId)}`);
	await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000);
	step('federation-reload', { roundCards: await ev(`document.querySelectorAll('[data-testid="round-cards"] li').length`), runStatus: out.api.run.body.status });
}
// ---- models ---------------------------------------------------------------------------------------------
await click('Models'); await waitFor(`location.pathname === '/app/models' && !!document.querySelector('[data-testid="candidate-card"]')`, 60000);
out.api.models = await api('/product/v1/models');
step('models', { candidates: await ev(`document.querySelectorAll('[data-testid="candidate-card"]').length`), released: await ev(text('released-models')), productionDeployed: await ev(`[...document.querySelectorAll('[data-testid="production-deployed"]')].map((e) => e.textContent.trim())`), acceptedCopy: (await body()).includes('ACCEPTED TO ENGINEERING SANDBOX REGISTRY'),
	controls: await ev(`[...document.querySelectorAll('button,a')].map((b) => b.textContent.trim()).filter((t) => /deploy|promote|default|switch|inference|use candidate/i.test(t))`) });
await shot('models');
// ---- research -------------------------------------------------------------------------------------------
await goto('/app/research/ml');
await waitFor(`document.body.innerText.includes('MODEL_V2_NOT_PROMOTED_RELEASE_CI') && document.body.innerText.includes('SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED')`, 60000);
out.api.ml = await api('/product/v1/research/ml'); const ml = await body();
step('research-ml', { status: out.api.ml.status, promotion: ml.includes('MODEL_V2_NOT_PROMOTED_RELEASE_CI'), softwareRelease: ml.includes('SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED'), calibrationCaveat: ml.includes('MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY'), provenance: ml.includes('EVIDENCE PROVENANCE') });
await goto('/app/research/fl');
await waitFor(`document.body.innerText.includes('V2-FL-004') && document.body.innerText.includes('V2-FL-005')`, 60000);
out.api.fl = await api('/product/v1/research/fl'); const fl = await body();
step('research-fl', { status: out.api.fl.status, phases: ['V2-FL-001', 'V2-FL-002', 'V2-FL-003', 'V2-FL-EVAL-001', 'V2-FL-004'].every((p) => fl.includes(p)), fedproxCaveat: fl.includes('NOT promoted as a generally superior method'), secaggCaveat: fl.includes('Protected aggregation interface only'), engineeringSeparate: fl.includes('V2-FL-005 is not scientific efficacy'), provenance: fl.includes('EVIDENCE PROVENANCE') });
await shot('research_fl');
// ---- system / hardware ------------------------------------------------------------------------------------
await click('System'); await waitFor(`location.pathname === '/app/system'`);
await waitFor(`document.body.innerText.includes('hardware_mode')`, 30000);
out.api.system = await api('/product/v1/system'); const sys = await body();
step('system', { hardwareMode: out.api.system.body.hardware_mode, physicalHardwareAvailable: out.api.system.body.physical_hardware_available, pageShowsSimulatedOnly: sys.includes('SIMULATED_ONLY'), pageShowsNoHardware: /physical_hardware_available\s*false/.test(sys.replace(/\n/g, ' ')) });
await goto('/app/about'); await waitFor(`document.body.innerText.includes('SIMULATED ONLY')`, 30000);
step('about', { noPhysicalWearable: (await body()).includes('No physical wearable is connected') });
out.sessionId = sessionId; out.runId = runId;
const host = new URL(ORIGIN).host;
const external = requests.filter((u) => { try { const x = new URL(u); return !['data:', 'blob:', 'about:'].includes(x.protocol) && !['127.0.0.1', 'localhost'].includes(x.hostname); } catch { return !/^(data|blob|about):/.test(u); } });
out.network = { requestCount: requests.length, origins: [...new Set(requests.map((u) => { try { return new URL(u).origin; } catch { return u.slice(0, 20); } }))], external, blockedExternal: blocked, websockets: [...new Set(sockets)], frontendHost: host };
out.console_errors = errors; out.elapsed_s = Math.round((Date.now() - t0) / 1000);
writeFileSync(OUT, JSON.stringify(out, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
