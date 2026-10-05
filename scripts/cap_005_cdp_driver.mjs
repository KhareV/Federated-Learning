// CAP-005 browser driver: drives REAL Chrome (CDP, no dependency) through the faculty DEMO flow against
// the real frontend build + real CAP-004 backend, and records evidence JSON. Usage:
//   node scripts/cap_005_cdp_driver.mjs <chromeDebugPort> <frontendOrigin> <outJson> <screenshotDir>
import { writeFileSync, mkdirSync } from 'node:fs';

const [, , debugPort, ORIGIN, OUT, SHOTS] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Cdp {
	constructor(url) {
		this.ws = new WebSocket(url);
		this.id = 0; this.pending = new Map(); this.handlers = [];
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
const page = targets.find((t) => t.type === 'page');
const cdp = new Cdp(page.webSocketDebuggerUrl);
await cdp.ready;

let phase = 'product';
const requests = []; const failures = []; const sockets = []; const consoleErrors = [];
cdp.on((method, p) => {
	if (method === 'Network.requestWillBeSent') requests.push({ url: p.request.url, type: p.type, phase });
	else if (method === 'Network.loadingFailed') failures.push({ id: p.requestId, error: p.errorText, type: p.type, phase });
	else if (method === 'Network.webSocketCreated') sockets.push(p.url);
	else if (method === 'Runtime.exceptionThrown') consoleErrors.push({ phase, text: String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200) });
	else if (method === 'Runtime.consoleAPICalled' && p.type === 'error') consoleErrors.push({ phase, text: p.args.map((a) => a.value ?? a.description).join(' ').slice(0, 200) });
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
const goto = async (path) => { await cdp.send('Page.navigate', { url: `${ORIGIN}${path}` }); await sleep(150); };
const text = (id) => `(document.querySelector('[data-testid="${id}"]')?.textContent ?? '').trim()`;
const clickText = (label) => ev(`(() => { const b = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)}); if (!b || b.disabled) return false; b.click(); return true; })()`);
const clickId = (id) => ev(`(() => { const b = document.querySelector('[data-testid="${id}"]'); if (!b || b.disabled) return false; b.click(); return true; })()`);
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
async function viewport(width, height = 900) { await cdp.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width <= 768 }); await sleep(350); }

const OVERFLOW = `(() => { const iw = innerWidth; const over = [...document.querySelectorAll('body *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > iw + 1 && !e.closest('.scroll,.plot,pre') && getComputedStyle(e).position !== 'fixed'; }).slice(0, 6).map((e) => e.tagName + '.' + String(e.className).slice(0, 40) + ' right=' + Math.round(e.getBoundingClientRect().right)); return { innerWidth: iw, scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, overflowing: over }; })()`;
const result = { origin: ORIGIN, steps: [] };
const step = (name, data = {}) => result.steps.push({ step: name, ...data });

// ---- 1-2: /sign-in, backend /system, DEMO ---------------------------------------------------
await viewport(1440);
await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`, 60000, 'demo sign-in');
const signinText = await ev('document.body.innerText');
step('sign-in', { title: signinText.includes('NHM OFFLINE FACULTY DEMO'), notClerk: signinText.includes('DEMO - NOT CLERK'), passwordField: await ev(`!!document.querySelector('input[type=password]')`), clerkGlobal: await ev(`typeof window.Clerk !== 'undefined'`), systemRequested: requests.some((r) => r.url.endsWith('/product/v1/system')) });
await shot('sign-in_1440');
// ---- 3-5: enter demo -> /app + banner + identity ---------------------------------------------
await clickText('ENTER DEMO WORKSPACE');
await waitFor(`location.pathname === '/app' && document.querySelector('[data-testid="demo-banner"]')`, 60000, '/app');
step('app-overview', { path: await ev('location.pathname'), banner: await ev(text('demo-banner')), identity: await ev(text('identity-chip')), overview: (await ev('document.body.innerText')).includes('MODEL_V2_FINAL') });
await shot('app_1440');
// ---- 6-12: device ----------------------------------------------------------------------------
await clickText('Device'); await waitFor(`location.pathname === '/app/device'`);
await waitFor(`document.body.innerText.includes('ATTACH NHM VIRTUAL WEARABLE')`);
const deviceStates = [];
step('device-empty', { simulationBanner: await ev(text('simulation-banner')), scenarios: await ev(`[...document.querySelectorAll('#scenario option')].map((o) => o.value)`), preselected: await ev(`document.querySelector('#scenario').value`) });
await shot('device_empty_1440');
await clickText('ATTACH NHM VIRTUAL WEARABLE'); await waitFor(`!!document.querySelector('[data-testid="device-state"]')`);
const deviceId = await ev(text('device-id')); deviceStates.push(await ev(text('device-state')));
step('device-attached', { deviceId, scenario: await ev(text('device-scenario')), physical: (await ev('document.body.innerText')).includes('NOT CONNECTED / NOT IMPLEMENTED') });
await clickText('SCAN'); await waitFor(`${text('device-state')} === 'FOUND'`); deviceStates.push('FOUND');
await clickText('PAIR / CONNECT'); await waitFor(`${text('device-state')} === 'CONNECTED'`); deviceStates.push('CONNECTED');
step('device-connected', { states: deviceStates });
await shot('device_connected_1440');
// ---- 13-17: monitoring session ---------------------------------------------------------------
await clickText('Monitor'); await waitFor(`location.pathname === '/app/monitoring'`);
await waitFor(`!!document.querySelector('[data-testid="create-session"]')`);
await ev(`window.__obs = { device: [], quality: [], monitoring: [], ctxUnavailable: 0, ctxAvailable: 0, gapVisible: 0, maxSegmentsWithGap: 0, sessionStates: [], events: 0, staleInference: 0 };
 const o = window.__obs; const push = (arr, v) => { if (v && arr[arr.length - 1] !== v) arr.push(v); };
 const read = () => { const g = (id) => document.querySelector('[data-testid="' + id + '"]');
  push(o.device, g('live-device-state')?.textContent.trim()); push(o.quality, g('quality-state')?.textContent.trim());
  push(o.monitoring, g('monitoring-state')?.textContent.trim()); push(o.sessionStates, g('session-state')?.textContent.trim());
  if (g('context-unavailable')) o.ctxUnavailable++; else if (document.body.innerText.includes('ECG HR')) o.ctxAvailable++;
  if (g('inference-stale')) o.staleInference++;
  const p = g('waveform-plot'); if (p && Number(p.getAttribute('data-visible-gaps')) > 0) { o.gapVisible++; o.maxSegmentsWithGap = Math.max(o.maxSegmentsWithGap, Number(p.getAttribute('data-segments'))); } };
 new MutationObserver(read).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true }); read();`);
await clickId('create-session');
await waitFor(`${text('session-state')} === 'DEVICE_READY'`);
const sessionId = await ev(text('session-id'));
step('session-created', { sessionId, state: await ev(text('session-state')) });
await waitFor(`${text('stream-status')}.includes('OPEN')`, 30000, 'socket open');
await clickId('start-session');
await waitFor(`!!document.querySelector('[data-testid="session-complete"]')`, 170000, 'session completion');
await sleep(500);
const obs = await ev('window.__obs');
const facts = await ev(`({ streamStatus: ${text('stream-status')}, sessionState: ${text('session-state')}, sessionComplete: ${text('session-complete')}, gapList: ${text('gap-list')}, stateChanges: [...document.querySelectorAll('[data-testid="state-changes"] li')].map((l) => l.textContent.trim()), qualityNote: [...document.querySelectorAll('p')].map((p) => p.textContent).find((t) => t.includes('ECG windows so far')) ?? '', infModel: ${text('inf-model')}, infCal: ${text('inf-cal')}, liveDevice: ${text('live-device-state')}, deviceChanges: [...document.querySelectorAll('[data-testid="live-device-state"] ~ ol li')].map((l) => l.textContent.trim()), streamError: ${text('stream-error')}, footnotes: document.body.innerText.includes('Simulated device-source ECG transport'), ppgNote: document.body.innerText.includes('PPG waveform is unavailable') })`);
step('monitoring-complete', { observed: obs, facts });
await shot('monitor_complete_1440');
// ---- responsive (monitor with data) ---------------------------------------------------------
const responsive = {};
for (const w of [1440, 1024, 768, 390]) {
	await viewport(w);
	responsive[`monitor_${w}`] = await ev(`(() => { const iw = innerWidth; const over = [...document.querySelectorAll('body *')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > iw + 1 && !e.closest('.scroll,.plot,pre') && getComputedStyle(e).position !== 'fixed'; }).slice(0, 5).map((e) => e.tagName + '.' + e.className); return { innerWidth: iw, scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, overflowing: over, menuVisible: !!document.querySelector('.menu') && getComputedStyle(document.querySelector('.menu')).display !== 'none', createVisible: !!document.querySelector('[data-testid="create-session"]'), plotWidth: document.querySelector('[data-testid="waveform-plot"]')?.getBoundingClientRect().width ?? 0 }; })()`);
	await shot(`monitor_${w}`);
}
await viewport(1440);
// ---- refresh: persisted session survives -----------------------------------------------------
await cdp.send('Page.reload'); await sleep(300);
await waitFor(`!!document.querySelector('[data-testid="demo-banner"]')`, 60000, 'reload bootstrap');
const afterReload = await ev(`(async () => { const r = await fetch('/product/v1/sessions/${sessionId}'); const s = await r.json(); const list = await (await fetch('/product/v1/sessions')).json(); return { status: r.status, state: s.state, model: s.runtime.model_id, listed: list.some((x) => x.session_id === '${sessionId}') }; })()`);
await clickText('History'); await waitFor(`location.pathname === '/app/history'`);
await waitFor(`!!document.querySelector('[data-testid="session-table"]')`);
const historyRow = await ev(`[...document.querySelectorAll('[data-testid="session-table"] tbody tr')].map((tr) => tr.innerText.replace(/\\s+/g, ' ')).find((t) => t.includes('${sessionId}')) ?? null`);
step('reload-persistence', { api: afterReload, historyRow });
await shot('history_1440');
await goto('/app/monitoring'); await waitFor(`document.body.innerText.includes('Monitoring session') && !!document.querySelector('[data-testid="simulation-banner"]')`);
await sleep(500);
const monitorText = await ev('document.body.innerText');
step('monitor-after-reload', { deviceStateMessage: monitorText.match(/Device [A-Z_0-9]+ is [A-Z]+/)?.[0] ?? null, createButtonPresent: await ev(`!!document.querySelector('[data-testid="create-session"]')`), liveWaveformPoints: await ev(`Number(document.querySelector('[data-testid="waveform-plot"]')?.dataset.points ?? 0)`), noPastLiveReplay: !monitorText.includes('LIVE STREAM') });
// ---- more responsive + accessibility on the product pages ------------------------------------
const pages = { sign_in: '/sign-in', overview: '/app', device: '/app/device', history: '/app/history', federation: '/app/federation', landing: '/' };
for (const [name, path] of Object.entries(pages)) {
	phase = name === 'landing' ? 'landing' : 'product';
	for (const w of [1440, 1024, 768, 390]) {
		await viewport(w); await goto(path); await sleep(name === 'landing' ? (w === 1440 ? 6500 : 1500) : 600);
		responsive[`${name}_${w}`] = await ev(OVERFLOW);
		if (name === 'landing' && w === 1440) result.landingText = await ev('document.body.innerText');
		if (w === 390 || w === 1440) await shot(`${name}_${w}`);
	}
}
await viewport(1440);
phase = 'product';
const a11y = {};
const a11yPages = { sign_in: '/sign-in', overview: '/app', device: '/app/device', monitoring: '/app/monitoring', history: '/app/history', federation: '/app/federation', models: '/app/models' };
const press = async (key, code, vk) => { for (const t of ['keyDown', 'keyUp']) await cdp.send('Input.dispatchKeyEvent', { type: t, key, code, windowsVirtualKeyCode: vk }); };
await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
for (const [name, path] of Object.entries(a11yPages)) {
	await goto(path); await waitFor(`document.querySelector('h1')`, 30000, `h1 on ${path}`); await sleep(400);
	const stat = await ev(`(() => { const named = (e) => (e.getAttribute('aria-label') || e.textContent || '').trim().length > 0 || !!e.getAttribute('aria-labelledby');
	 return { h1: document.querySelectorAll('h1').length, main: document.querySelectorAll('main').length, lang: document.documentElement.lang, nav: [...document.querySelectorAll('nav')].every((n) => n.getAttribute('aria-label')), skipLink: !!document.querySelector('a.skip'),
	  unnamedButtons: [...document.querySelectorAll('button,a[href]')].filter((e) => !named(e)).length, unlabelledSelects: [...document.querySelectorAll('select')].filter((s) => !s.getAttribute('aria-label') && !(s.id && document.querySelector('label[for="' + s.id + '"]'))).length,
	  liveRegions: document.querySelectorAll('[aria-live],[role=status],[role=alert]').length, runningAnimations: document.getAnimations().filter((a) => a.playState === 'running').length, imagesWithoutAlt: [...document.querySelectorAll('img')].filter((i) => !i.hasAttribute('alt')).length }; })()`);
	const focus = [];
	for (let i = 0; i < 8; i += 1) {
		await press('Tab', 'Tab', 9); await sleep(40);
		focus.push(await ev(`(() => { const e = document.activeElement; if (!e || e === document.body) return null; const cs = getComputedStyle(e); return { tag: e.tagName, name: (e.getAttribute('aria-label') || e.textContent || '').trim().slice(0, 30), outline: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 }; })()`));
	}
	result.renderedText = { ...(result.renderedText ?? {}), [name]: await ev('document.body.innerText') };
	a11y[name] = { ...stat, focusSequence: focus, focusableReached: focus.filter(Boolean).length, allFocusVisible: focus.filter(Boolean).every((f) => f.outline) };
}
await cdp.send('Emulation.setEmulatedMedia', { features: [] });
// ---- offline / network audit ----------------------------------------------------------------
const scheme = (u) => u.split(':')[0];
const originOf = (u) => (/^https?:|^wss?:/.test(u) ? new URL(u).origin : `${scheme(u)}:`);
const isLocal = (r) => /^(data|blob|about):/.test(r.url) || originOf(r.url) === ORIGIN;
const byPhase = (ph) => requests.filter((r) => r.phase === ph);
result.network = { requestCount: requests.length, productPhaseRequestCount: byPhase('product').length, landingPhaseRequestCount: byPhase('landing').length,
	origins: [...new Set(requests.map((r) => originOf(r.url)))], productPhaseOrigins: [...new Set(byPhase('product').map((r) => originOf(r.url)))],
	external: [...new Set(requests.filter((r) => !isLocal(r)).map((r) => originOf(r.url)))], externalInProductPhase: [...new Set(byPhase('product').filter((r) => !isLocal(r)).map((r) => originOf(r.url)))],
	topProductPaths: Object.entries(requests.filter((r) => r.phase === 'product').reduce((m, r) => { const k = (() => { try { return new URL(r.url).pathname.replace(/\/_app\/immutable\/.*/, '/_app/immutable/*').replace(/SESS-[0-9a-f]+/, '{session}'); } catch { return r.url.slice(0, 20); } })(); m[k] = (m[k] ?? 0) + 1; return m; }, {})).sort((a, b) => b[1] - a[1]).slice(0, 8),
	inlineDataRequests: requests.filter((r) => r.url.startsWith('data:')).length, clerkRequests: requests.filter((r) => /clerk/i.test(r.url)).length, failures, websockets: sockets,
	inferWindowFromBrowser: requests.some((r) => r.url.includes('infer-window')), productRequests: [...new Set(requests.filter((r) => r.url.includes('/product/v1')).map((r) => new URL(r.url).pathname.replace(/SESS-[0-9a-f]+/, '{session}').replace(/NHM_VIRTUAL_WEARABLE_\d+/, '{device}')))].sort() };
result.responsive = responsive; result.accessibility = a11y; result.consoleErrors = consoleErrors; result.deviceId = deviceId; result.sessionId = sessionId;
writeFileSync(OUT, JSON.stringify(result, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
