// CAP-009 canonical REAL Chrome browser flow; no external network or fake data.
// node scripts/cap_009_cdp_driver.mjs <debugPort> <frontendOrigin> <outJson> <shotDir>
import { writeFileSync, mkdirSync } from 'node:fs';

const [, , debugPort, ORIGIN, OUT, SHOTS] = process.argv;
mkdirSync(SHOTS, { recursive: true });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
class Cdp {
	constructor(url) {
		this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
		this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
		this.ws.onmessage = (message) => {
			const event = JSON.parse(message.data);
			if (event.id && this.pending.has(event.id)) {
				const { resolve, reject } = this.pending.get(event.id); this.pending.delete(event.id);
				event.error ? reject(new Error(JSON.stringify(event.error))) : resolve(event.result);
			} else if (event.method) for (const handler of this.handlers) handler(event.method, event.params);
		};
	}
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params }));
		return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject })); }
	on(handler) { this.handlers.push(handler); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((target) => target.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const requests = [], errors = [], blockedExternal = [];
cdp.on((method, params) => {
	if (method === 'Network.requestWillBeSent') requests.push(params.request.url);
	if (method === 'Fetch.requestPaused') {
		const url = params.request.url;
		let allowed = false;
		try { allowed = ['127.0.0.1', 'localhost'].includes(new URL(url).hostname); }
		catch { allowed = /^(data|blob|about):/.test(url); }
		if (!allowed) blockedExternal.push(url);
		void cdp.send(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest',
			allowed ? { requestId: params.requestId } : { requestId: params.requestId, errorReason: 'BlockedByClient' })
			.catch((error) => errors.push(`REQUEST_INTERCEPTION:${String(error)}`));
	}
	if (method === 'Runtime.exceptionThrown') errors.push(String(params.exceptionDetails?.exception?.description ?? params.exceptionDetails?.text));
	if (method === 'Runtime.consoleAPICalled' && params.type === 'error') errors.push(params.args.map((arg) => arg.value ?? arg.description).join(' '));
});
for (const domain of ['Page','Runtime','Network']) await cdp.send(`${domain}.enable`);
await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
async function ev(expression) {
	const response = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
	if (response.exceptionDetails) throw new Error(`BROWSER_EVAL:${JSON.stringify(response.exceptionDetails).slice(0, 250)}`);
	return response.result.value;
}
async function waitFor(expression, timeout = 120000) {
	const until = Date.now() + timeout;
	while (Date.now() < until) {
		let result = null; try { result = await ev(expression); } catch { /* navigation in progress */ }
		if (result) return result;
		await sleep(100);
	}
	throw new Error(`BROWSER_TIMEOUT:${expression}`);
}
async function goto(path) { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(200); }
const click = async (label) => ev(`(() => { const e = [...document.querySelectorAll('button,a')].find((x) => x.textContent.trim() === ${JSON.stringify(label)}); if (!e || e.disabled) return false; e.click(); return true; })()`);
const clickId = async (id) => ev(`(() => { const e = document.querySelector('[data-testid="${id}"]'); if (!e || e.disabled) return false; e.click(); return true; })()`);
const text = (id) => `(document.querySelector('[data-testid="${id}"]')?.textContent ?? '').trim()`;
async function shot(name) { const result = await cdp.send('Page.captureScreenshot', { format: 'png' });
	writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(result.data, 'base64')); }
async function viewport(width) { await cdp.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width <= 768 }); await sleep(250); }
async function api(path) { return ev(`fetch(${JSON.stringify(path)}).then(async (r) => ({ status: r.status, body: await r.json() }))`); }
const output = { steps: [], responsive: {}, accessibility: {}, requests: [], console_errors: [] };
const step = (name, result) => output.steps.push({ name, ...result });

await viewport(1440);
await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
await click('ENTER DEMO WORKSPACE');
await waitFor(`location.pathname === '/app' && !!document.querySelector('[data-testid="demo-banner"]')`);
step('auth', { mode: 'DEMO', clerk_initialized: await ev(`typeof window.Clerk !== 'undefined'`) });
await click('Device'); await waitFor(`location.pathname === '/app/device'`);
await click('ATTACH NHM VIRTUAL WEARABLE');
await waitFor(`!!document.querySelector('[data-testid="device-state"]')`);
const deviceId = await ev(text('device-id'));
await click('SCAN'); await waitFor(`${text('device-state')} === 'FOUND'`);
await click('PAIR / CONNECT'); await waitFor(`${text('device-state')} === 'CONNECTED'`);
step('device', { device_id: deviceId, state: 'CONNECTED' });
await click('Monitor'); await waitFor(`location.pathname === '/app/monitoring'`);
await clickId('create-session'); await waitFor(`${text('session-state')} === 'DEVICE_READY'`);
const sessionId = await ev(text('session-id'));
await waitFor(`${text('stream-status')}.includes('OPEN')`, 30000);
await clickId('start-session');
await waitFor(`!!document.querySelector('[data-testid="session-complete"]')`, 200000);
step('monitoring', { session_id: sessionId, state: await ev(text('session-state')) });

await click('History'); await waitFor(`location.pathname === '/app/history'`);
await waitFor(`!!document.querySelector('[data-testid="session-table"]')`);
const listed = await ev(`[...document.querySelectorAll('[data-testid="session-table"] tbody tr')].some((r) => r.textContent.includes(${JSON.stringify(sessionId)}))`);
step('history-list', { session_id: sessionId, listed });
const detailPath = `/app/history/${encodeURIComponent(sessionId)}`;
await goto(detailPath);
await waitFor(`document.body.innerText.includes('Persisted session summary') && document.body.innerText.includes('Bounded decimated ECG preview')`, 60000);
const summary = await api(`/product/v1/sessions/${encodeURIComponent(sessionId)}/summary`);
const timeline = await api(`/product/v1/sessions/${encodeURIComponent(sessionId)}/timeline`);
const session = await api(`/product/v1/sessions/${encodeURIComponent(sessionId)}`);
step('history-detail', { summary_status: summary.status, timeline_status: timeline.status,
		preview_count: timeline.body.waveform_previews?.length ?? 0,
		count_basis_visible: await ev(`document.body.innerText.includes('PERSISTED INFERENCE EVENTS')`),
		time_domain_separate: await ev(`document.body.innerText.includes('SOURCE DOMAIN') && document.body.innerText.includes('PRODUCT CLOCK')`),
		probability_copy: await ev(`document.body.innerText.includes('RESEARCH TECHNICAL METADATA')`),
		preview_svg_paths: await ev(`document.querySelectorAll('svg path').length`) });
await shot('history_detail_1440');

await goto('/app/research/ml');
await waitFor(`document.body.innerText.includes('MODEL_V2_NOT_PROMOTED_RELEASE_CI') && document.body.innerText.includes('SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED')`);
const ml = await api('/product/v1/research/ml');
step('research-ml', { status: ml.status, promotion: await ev(`document.body.innerText.includes('MODEL_V2_NOT_PROMOTED_RELEASE_CI')`),
	software_release: await ev(`document.body.innerText.includes('SYSTEM_V2_RESEARCH_DEFAULT_ACCEPTED')`),
	calibration_caveat: await ev(`document.body.innerText.includes('MIT-BIH SOURCE-DOMAIN CALIBRATION ONLY')`),
	provenance: await ev(`document.body.innerText.includes('EVIDENCE PROVENANCE')`) });
await shot('research_ml_1440');
await goto('/app/research/fl');
await waitFor(`document.body.innerText.includes('V2-FL-004') && document.body.innerText.includes('V2-FL-005')`);
const fl = await api('/product/v1/research/fl');
step('research-fl', { status: fl.status,
	phases: await ev(`['V2-FL-001','V2-FL-002','V2-FL-003','V2-FL-EVAL-001','V2-FL-004'].every((p) => document.body.innerText.includes(p))`),
	fedprox_caveat: await ev(`document.body.innerText.includes('NOT promoted as a generally superior method')`),
	secagg_caveat: await ev(`document.body.innerText.includes('Protected aggregation interface only')`),
	engineering_separate: await ev(`document.body.innerText.includes('V2-FL-005 is not scientific efficacy')`),
	provenance: await ev(`document.body.innerText.includes('EVIDENCE PROVENANCE')`) });
await shot('research_fl_1440');

for (const path of ['/app/history', detailPath, '/app/research/ml', '/app/research/fl']) {
	for (const width of [1440,1024,768,390]) {
		await viewport(width); await goto(path); await waitFor(`!!document.querySelector('h1')`); await sleep(350);
		output.responsive[`${path}@${width}`] = await ev(`({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })`);
		if (width === 390) await shot(`${path.replaceAll('/', '_').replaceAll('%','_')}_390`);
	}
	await viewport(1440);
	output.accessibility[path] = await ev(`({ h1: document.querySelectorAll('h1').length, main: document.querySelectorAll('main').length,
		unnamed_buttons: [...document.querySelectorAll('button')].filter((b) => !(b.getAttribute('aria-label') || b.textContent || '').trim()).length,
		unlabelled_selects: [...document.querySelectorAll('select')].filter((s) => !s.getAttribute('aria-label') && !document.querySelector('label[for="' + s.id + '"]')).length })`);
}
const external = requests.filter((url) => {
	try { const parsed = new URL(url); return !['127.0.0.1','localhost'].includes(parsed.hostname); }
	catch { return !/^(data|blob|about):/.test(url); }
});
output.requests = requests;
output.external_requests = external;
output.blocked_external_requests = blockedExternal;
output.console_errors = errors;
output.session_id = sessionId;
output.api = { session, summary, timeline, ml, fl };
writeFileSync(OUT, JSON.stringify(output, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
