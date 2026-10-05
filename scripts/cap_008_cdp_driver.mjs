// CAP-008 browser driver: REAL headless Chrome (CDP, no dependency) drives the federation product flow against the
// production CAPSTONE_UI_V1_1 build + the real CAP-007 backend (DEMO, offline). Records evidence JSON.
//   node scripts/cap_008_cdp_driver.mjs <chromeDebugPort> <frontendOrigin> <outJson> <screenshotDir>
import { writeFileSync, mkdirSync } from 'node:fs';

const [, , debugPort, ORIGIN, OUT, SHOTS] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Cdp {
	constructor(url) {
		this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
		this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
		this.ws.onmessage = (m) => {
			const msg = JSON.parse(m.data);
			if (msg.id && this.pending.has(msg.id)) { const { res, rej } = this.pending.get(msg.id); this.pending.delete(msg.id); msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result); }
			else if (msg.method) for (const h of this.handlers) h(msg.method, msg.params);
		};
	}
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
	on(h) { this.handlers.push(h); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const requests = [], sockets = [], consoleErrors = [];
cdp.on((method, p) => {
	if (method === 'Network.requestWillBeSent') requests.push({ url: p.request.url, type: p.type });
	else if (method === 'Network.webSocketCreated') sockets.push(p.url);
	else if (method === 'Runtime.exceptionThrown') consoleErrors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200));
	else if (method === 'Runtime.consoleAPICalled' && p.type === 'error') consoleErrors.push(p.args.map((a) => a.value ?? a.description).join(' ').slice(0, 200));
});
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
async function ev(expression) {
	const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
	if (r.exceptionDetails) throw new Error(`eval failed: ${expression.slice(0, 80)} :: ${JSON.stringify(r.exceptionDetails).slice(0, 200)}`);
	return r.result.value;
}
async function waitFor(expression, timeoutMs = 60000, label = expression) {
	const t0 = Date.now();
	for (;;) {
		let v; try { v = await ev(expression); } catch { v = null; }
		if (v) return v;
		if (Date.now() - t0 > timeoutMs) throw new Error(`timeout waiting for: ${label}`);
		await sleep(50);
	}
}
const goto = async (path) => { await cdp.send('Page.navigate', { url: `${ORIGIN}${path}` }); await sleep(200); };
const text = (id) => `(document.querySelector('[data-testid="${id}"]')?.textContent ?? '').trim()`;
const clickText = (label) => ev(`(() => { const b = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)}); if (!b || b.disabled) return false; b.click(); return true; })()`);
const clickId = (id) => ev(`(() => { const b = document.querySelector('[data-testid="${id}"]'); if (!b || b.disabled) return false; b.click(); return true; })()`);
const setSelect = (id, value) => ev(`(() => { const s = document.querySelector('[data-testid="${id}"]'); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return s.value; })()`);
const getJson = (path) => ev(`fetch(${JSON.stringify(path)}).then((r) => r.json())`);
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
async function viewport(width, height = 900) { await cdp.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width <= 768 }); await sleep(350); }
const OVERFLOW = `(() => { const iw = innerWidth; const over = [...document.querySelectorAll('body *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > iw + 1 && !e.closest('.tl,pre') && getComputedStyle(e).position !== 'fixed'; }).slice(0, 6).map((e) => e.tagName + '.' + String(e.className).slice(0, 40) + ' right=' + Math.round(e.getBoundingClientRect().right)); return { innerWidth: iw, scrollWidth: document.documentElement.scrollWidth, overflowing: over }; })()`;
const SAMPLE = `(() => { const q = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim(); const states = [...document.querySelectorAll('[data-testid="client-grid"] [data-state]')].map((e) => e.getAttribute('data-state')); return { status: q('run-status'), updates: q('update-ready-count'), submitted: q('submitted-count'), secagg: q('secagg-status'), agg: q('authoritative-aggregate'), rounds: [...document.querySelectorAll('[data-testid="round-states"] li')].map((e) => e.textContent.trim().slice(0, 60)), clientStates: states, submittedClients: states.filter((s) => s === 'SUBMITTED').length, trainingClients: states.filter((s) => s === 'TRAINING').length, candidate: q('candidate-live'), streamError: !!document.querySelector('[data-testid="stream-error"]') }; })()`;

const result = { origin: ORIGIN, steps: [] };
const step = (name, data = {}) => { result.steps.push({ step: name, ...data }); };
const t0 = Date.now();

// ---- 1-4 sign-in, DEMO, /app --------------------------------------------------------------------
await viewport(1440);
await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`, 60000, 'demo sign-in');
await clickText('ENTER DEMO WORKSPACE');
await waitFor(`location.pathname === '/app' && document.querySelector('[data-testid="demo-banner"]')`, 60000, '/app');
await waitFor(`document.body.innerText.includes('ENGINEERING RUNTIME ENABLED')`, 30000, 'federation enabled on /app');
const appText = await ev('document.body.innerText');
step('app-overview', { path: await ev('location.pathname'), federationEnabled: appText.includes('ENGINEERING RUNTIME ENABLED'), notYetEnabled: appText.includes('NOT YET ENABLED'), releasedModel: appText.includes('MODEL_V2_FINAL'), candidatesOnOverview: await ev(text('overview-candidate-count')) });
await shot('app_1440');

// ---- 5-7 federation overview + 8 real clients (cold start) -------------------------------------
await clickText('Federation');
await waitFor(`location.pathname === '/app/federation'`);
const preparingSeen = await ev(`!!document.querySelector('[data-testid="clients-preparing"]')`);
await waitFor(`document.body.innerText.includes('8 logical clients ready')`, 120000, '8 clients');
const fedText = await ev('document.body.innerText');
const overviewBefore = await getJson('/product/v1/federation');
step('federation-overview', { preparingSeen, clientsReady: true, banners: ['ENGINEERING FEDERATION DEMO', 'SIMULATED CLIENTS', 'NOT CLINICAL', 'NOT DEPLOYED'].map((b) => [b, fedText.includes(b)]), lanes: fedText.includes('Lane A · Released monitoring') && fedText.includes('Lane B · Federated development'), overviewBefore });
await shot('federation_1440');

// ---- 8-11 configuration -------------------------------------------------------------------------
const cfgBefore = await ev(`({ selects: document.querySelectorAll('select').length, inputs: document.querySelectorAll('input').length, runTypes: [...document.querySelector('[data-testid="cfg-run-type"]').options].map((o) => o.value), algorithms: [...document.querySelector('[data-testid="cfg-algorithm"]').options].map((o) => o.value), modes: [...document.querySelector('[data-testid="cfg-mode"]').options].map((o) => o.value), fixed: document.querySelector('[aria-label="Fixed configuration"]').innerText })`);
await setSelect('cfg-run-type', 'LIVE_RUN'); await setSelect('cfg-algorithm', 'FEDAVG'); await setSelect('cfg-mode', 'SECAGG_SHADOW');
step('configuration', { ...cfgBefore, chosen: await ev(`({ r: document.querySelector('[data-testid="cfg-run-type"]').value, a: document.querySelector('[data-testid="cfg-algorithm"]').value, m: document.querySelector('[data-testid="cfg-mode"]').value })`), roundOneShadowWording: (await ev('document.body.innerText')).includes('ROUND-1 PROTECTED-AGGREGATION SHADOW') });
const wsBefore = sockets.length;

// ---- 12-24 create -> WebSocket -> start -> observe ---------------------------------------------
await clickId('cfg-submit');
await waitFor(`location.pathname === '/app/federation/live' && ${text('run-status')}.length > 0`, 60000, 'live page');
const liveUrl = await ev('location.pathname + location.search');
const runId = new URL(ORIGIN + liveUrl).searchParams.get('run');
const samples = [];
let maxSubmittedR1 = 0, sawShadowRunning = false, sawShadowVerified = false, sawTraining = false, sawRound = new Set(), aggModes = new Set();
const deadline = Date.now() + 420000;
for (;;) {
	const s = await ev(SAMPLE);
	samples.push({ t: Date.now() - t0, status: s.status.slice(0, 40), updates: s.updates, submitted: s.submitted, round: s.rounds.length });
	maxSubmittedR1 = Math.max(maxSubmittedR1, s.submittedClients);
	if (s.secagg.includes('SHADOW_RUNNING')) sawShadowRunning = true;
	if (s.secagg.includes('SHADOW_VERIFIED')) sawShadowVerified = true;
	if (s.trainingClients > 0) sawTraining = true;
	for (const r of s.rounds) sawRound.add(r.slice(0, 8));
	if (s.agg.includes('PLAIN')) aggModes.add('PLAIN');
	if (s.streamError) throw new Error('stream error in browser');
	if (s.status.includes('COMPLETED') || s.status.includes('FAILED')) break;
	if (Date.now() > deadline) throw new Error('live run timeout');
	await sleep(150);
}
const live1 = await ev(SAMPLE);
const live1Text = await ev('document.body.innerText');
const secagg1 = live1Text.match(/SHADOW_RUNNING → SHADOW_VERIFIED/)?.[0] ?? null;
const newSockets = sockets.slice(wsBefore);
step('live-run-1', { runId, liveUrl, final: live1, samplesCount: samples.length, sampleSketch: samples.filter((_, i) => i % Math.max(1, Math.floor(samples.length / 12)) === 0), sawTraining, maxClientsSubmittedAtOnce: maxSubmittedR1, sawShadowRunningLive: sawShadowRunning, sawShadowVerifiedLive: sawShadowVerified, secagg_sequence_text: secagg1, roundsSeen: [...sawRound], aggregationModesSeen: [...aggModes], websocketUrls: newSockets,
	websocketUrlsCarryNoSecret: newSockets.every((u) => !/token|secret|bearer|session|user/i.test(u)), apiRun: await getJson(`/product/v1/federation/runs/${runId}`), apiRounds: await getJson(`/product/v1/federation/runs/${runId}/rounds`) });
await shot('live_completed_1440');

// ---- 25-28 models page --------------------------------------------------------------------------
await clickText('Models');
await waitFor(`location.pathname === '/app/models' && document.querySelector('[data-testid="candidate-card"]')`, 60000, 'models');
const models1 = await getJson('/product/v1/models');
const modelsDom = await ev(`({ released: document.querySelector('[data-testid="released-models"]').innerText, candidates: document.querySelectorAll('[data-testid="candidate-card"]').length, productionDeployed: [...document.querySelectorAll('[data-testid="production-deployed"]')].map((e) => e.textContent), accepted: document.body.innerText.includes('ACCEPTED TO ENGINEERING SANDBOX REGISTRY'), buttons: [...document.querySelectorAll('button,a')].map((b) => b.textContent.trim()).filter((t) => /deploy|promote|default|switch|inference|use candidate/i.test(t)) })`);
step('models', { registryApi: models1, dom: modelsDom });
await shot('models_1440');

// ---- 29-30 privacy ------------------------------------------------------------------------------
await goto(`/app/federation/privacy?run=${runId}`);
await waitFor(`document.querySelector('[data-testid="privacy-secagg"]')?.textContent.includes('SHADOW_VERIFIED')`, 60000, 'privacy secagg status');
const privText = await ev('document.body.innerText');
step('privacy', { roundOneOnly: privText.includes('round 1 only') || privText.includes('ROUND 1 ONLY') || privText.includes('for round 1 only'), shadowWording: privText.includes('ROUND-1 PROTECTED-AGGREGATION SHADOW'), authoritativePlain: privText.includes('Authoritative aggregation remains PLAIN'), authoritativeAggregateLine: await ev(text('privacy-agg')), secaggLine: await ev(text('privacy-secagg')),
	claims: { differentialPrivacyClaimed: /differentially private|provides differential privacy/i.test(privText), noDifferentialPrivacyStated: privText.includes('No differential privacy.'), anonymityClaimed: /anonymous (training|federation)|guarantees anonymity/i.test(privText), noAnonymityStated: privText.includes('No anonymity guarantee.') } });
await shot('privacy_1440');

// ---- 31-32 refresh: persisted run + candidate reload --------------------------------------------
await goto(`/app/federation/rounds?run=${runId}`);
await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000, 'rounds after reload');
const roundCards = await ev(`[...document.querySelectorAll('[data-testid="round-cards"] li')].map((e) => e.innerText.replace(/\\s+/g, ' '))`);
const lineage = await ev(text('lineage'));
await Page_reload();
await waitFor(`document.querySelectorAll('[data-testid="round-cards"] li').length === 3`, 60000, 'rounds after refresh');
await goto('/app/models');
await waitFor(`document.querySelector('[data-testid="candidate-card"]')`, 60000, 'models after reload');
step('reload-persistence', { roundCards, lineage, lineageMentionsReleasedModel: lineage.includes('MODEL_V2_FINAL'), candidatesAfterReload: await ev(`document.querySelectorAll('[data-testid="candidate-card"]').length`), runStillListed: (await getJson('/product/v1/federation/runs')).some((r) => r.run_id === runId) });
async function Page_reload() { await cdp.send('Page.reload'); await sleep(400); }

// ---- REPLAY flow --------------------------------------------------------------------------------
const before = { overview: await getJson('/product/v1/federation'), models: (await getJson('/product/v1/models')).capstone_fl_candidates.length };
await goto('/app/federation');
await waitFor(`document.querySelector('[data-testid="cfg-run-type"]')`, 60000, 'config');
await setSelect('cfg-run-type', 'REPLAY'); await setSelect('cfg-algorithm', 'FEDAVG'); await setSelect('cfg-mode', 'SECAGG_SHADOW');
const replayHelp = await ev('document.body.innerText');
await clickId('cfg-submit');
await waitFor(`location.pathname === '/app/federation/live' && ${text('run-status')}.includes('COMPLETED')`, 120000, 'replay completed');
const rs = await ev(SAMPLE);
const rtext = await ev('document.body.innerText');
const replayRun = new URL(ORIGIN + (await ev('location.pathname + location.search'))).searchParams.get('run');
const after = { overview: await getJson('/product/v1/federation'), models: (await getJson('/product/v1/models')).capstone_fl_candidates.length };
step('replay', { replayRunId: replayRun, helpSaysNoTraining: replayHelp.includes('No training is executed.'), badge: await ev(text('replay-badge')), note: await ev(text('replay-note')), historicalCandidate: await ev(text('historical-candidate')),
	trainingClaims: /training in progress|clients are computing|TRAINING IN PROGRESS/i.test(rtext), final: rs, run: await getJson(`/product/v1/federation/runs/${replayRun}`), candidateCountBefore: before.models, candidateCountAfter: after.models, overviewCandidateBefore: before.overview.candidate_count, overviewCandidateAfter: after.overview.candidate_count,
	updateReady: rs.updates, replayedEventLabels: rtext.includes('REPLAYED EVENT') });
await shot('replay_1440');

// ---- refresh DURING a genuine live run ---------------------------------------------------------
await goto('/app/federation');
await waitFor(`document.querySelector('[data-testid="cfg-run-type"]')`, 60000, 'config 2');
await setSelect('cfg-run-type', 'LIVE_RUN'); await setSelect('cfg-algorithm', 'FEDAVG'); await setSelect('cfg-mode', 'PLAIN');
const socketsBeforeSecond = sockets.length;
await clickId('cfg-submit');
await waitFor(`location.pathname === '/app/federation/live' && Number(${text('update-ready-count')} || 0) >= 9`, 180000, 'mid-run');
const midUrl = await ev('location.pathname + location.search');
const midRun = new URL(ORIGIN + midUrl).searchParams.get('run');
const midBefore = await ev(SAMPLE);
await Page_reload();
await waitFor(`document.body.innerText.includes('Live federation') && ${text('run-status')}.length > 0`, 60000, 'live page after refresh');
const midAfterEarly = await ev(SAMPLE);
let dup = false, maxUpdates = 0;
const d2 = Date.now() + 420000;
for (;;) {
	const s = await ev(SAMPLE);
	const u = Number(s.updates || 0); maxUpdates = Math.max(maxUpdates, u);
	if (u > 24 || s.streamError) dup = true;
	if (s.status.includes('COMPLETED') || s.status.includes('FAILED')) break;
	if (Date.now() > d2) throw new Error('second live run timeout');
	await sleep(150);
}
const midFinal = await ev(SAMPLE);
step('refresh-during-run', { runId: midRun, urlKeptRun: midUrl.includes(`run=${midRun}`), before: { updates: midBefore.updates, status: midBefore.status }, afterRefreshEarly: { updates: midAfterEarly.updates, status: midAfterEarly.status, authRestored: (await ev('location.pathname')) === '/app/federation/live' },
	websocketsCreatedForSecondRun: sockets.length - socketsBeforeSecond, final: midFinal, maxUpdateReadyObserved: maxUpdates, doubleCounted: dup, sequenceError: midFinal.streamError, apiRun: await getJson(`/product/v1/federation/runs/${midRun}`), candidateCountAfter: (await getJson('/product/v1/models')).capstone_fl_candidates.length });

// ---- responsive / accessibility ----------------------------------------------------------------
const responsive = {};
for (const w of [1440, 1024, 768, 390]) {
	await viewport(w);
	const per = {};
	for (const path of ['/app/federation', '/app/federation/clients', `/app/federation/rounds?run=${runId}`, `/app/federation/live?run=${runId}`, `/app/federation/privacy?run=${runId}`, '/app/models']) {
		await goto(path); await sleep(1500);
		per[path.split('?')[0]] = await ev(OVERFLOW);
		per[path.split('?')[0]].fitsViewport = per[path.split('?')[0]].innerWidth === w && per[path.split('?')[0]].scrollWidth <= w && per[path.split('?')[0]].overflowing.length === 0;
	}
	responsive[w] = per;
	await goto(`/app/federation/live?run=${runId}`); await sleep(1500); await shot(`live_${w}`);
}
step('responsive', { widths: responsive });
await viewport(1440);
await goto(`/app/federation/live?run=${runId}`); await sleep(1500);
step('accessibility', await ev(`(() => { const sel = [...document.querySelectorAll('select')]; return { h1: document.querySelectorAll('h1').length, headings: [...document.querySelectorAll('h1,h2,h3')].length, mainLandmark: !!document.querySelector('main'), skipLink: !!document.querySelector('a.skip'), liveRegion: !!document.querySelector('[aria-live]'), statusRole: !!document.querySelector('[role="status"]'), selectsLabelled: sel.every((s) => !!s.closest('label') || s.getAttribute('aria-label')), buttonsNamed: [...document.querySelectorAll('button')].every((b) => (b.textContent || b.getAttribute('aria-label') || '').trim().length > 0), clientGridLabelled: !!document.querySelector('[data-testid="client-grid"][aria-label]'), stateAlsoText: [...document.querySelectorAll('[data-testid="client-grid"] .st')].every((e) => e.textContent.trim().length > 0), runningAnimations: document.getAnimations().length }; })()`));
await goto('/app/federation'); await sleep(1500);
step('keyboard', await ev(`(() => { const s = document.querySelector('[data-testid="cfg-run-type"]'); s.focus(); return { focusable: document.activeElement === s, focusVisibleCssRule: [...document.styleSheets].some((sh) => { try { return [...sh.cssRules].some((r) => /focus-visible/.test(r.cssText)); } catch { return false; } }) }; })()`));

// ---- network ------------------------------------------------------------------------------------
const host = new URL(ORIGIN).host;
const external = requests.filter((r) => { try { const u = new URL(r.url); return !['data:', 'blob:', 'about:'].includes(u.protocol) && u.host !== host; } catch { return false; } });
result.network = { requestCount: requests.length, origins: [...new Set(requests.map((r) => { try { return new URL(r.url).origin; } catch { return r.url.slice(0, 20); } }))], external, websockets: [...new Set(sockets)] };
result.console_errors = consoleErrors;
result.elapsed_s = Math.round((Date.now() - t0) / 1000);
writeFileSync(OUT, JSON.stringify(result, null, 1));
cdp.ws.close();
process.exit(0);
