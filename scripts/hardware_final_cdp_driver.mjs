// Real Chrome + real Clerk + real Atlas hardware-monitoring scenarios.
// Credentials are read from an ignored temporary file and never written to output.
import { readFileSync, writeFileSync, mkdirSync, openSync, closeSync } from 'node:fs';
import { spawn } from 'node:child_process';

const [, , MODE, debugPort, ORIGIN, USERS, OUT, SHOTS, LOGS] = process.argv;
const user = JSON.parse(readFileSync(USERS))[process.env.NHM_BROWSER_USER ?? 'A'];
mkdirSync(SHOTS, { recursive: true }); mkdirSync(LOGS, { recursive: true });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
class Cdp {
	constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; }); this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const p = this.pending.get(e.id); this.pending.delete(e.id); e.error ? p.rej(new Error(JSON.stringify(e.error))) : p.res(e.result); } }; }
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl); await cdp.ready;
for (const domain of ['Page', 'Runtime', 'Network']) await cdp.send(`${domain}.enable`);
await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails)); return r.result.value; }
async function waitFor(expression, timeout = 120000) { const end = Date.now() + timeout; while (Date.now() < end) { try { const v = await ev(expression); if (v) return v; } catch {} await sleep(150); } throw new Error(`timeout:${expression}`); }
async function goto(path) { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(500); }
async function shot(name) { const r = await cdp.send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(r.data, 'base64')); }
const clickId = (id) => ev(`(() => { const e=document.querySelector('[data-testid=${JSON.stringify(id)}]'); if(!e||e.disabled)return false;e.click();return true;})()`);
const value = (id) => ev(`(document.querySelector('[data-testid=${JSON.stringify(id)}]')?.textContent ?? '').trim()`);
const attr = (id, name) => ev(`document.querySelector('[data-testid=${JSON.stringify(id)}]')?.getAttribute(${JSON.stringify(name)}) ?? null`);
const setSelect = (selector, val) => ev(`(() => {const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(val)};e.dispatchEvent(new Event('change',{bubbles:true}));return e.value;})()`);
async function signIn() {
	await goto('/sign-in'); await waitFor(`!!document.querySelector('input[name=identifier]')`, 60000);
	await ev(`document.querySelector('input[name=identifier]').focus()`); await cdp.send('Input.insertText', { text: user.email }); await sleep(400);
	await ev(`([...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue')).click()`); await waitFor(`!!document.querySelector('input[name=password]')`, 30000);
	await sleep(1500); await ev(`document.querySelector('input[name=password]').focus()`); await cdp.send('Input.insertText', { text: user.password }); await sleep(600);
	await ev(`([...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue')).click()`);
	await sleep(4000);
	if ((await ev('location.pathname')).startsWith('/sign-in') && /Enter your password/.test(await ev('document.body.innerText'))) {
		await ev(`([...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue')).click()`);
	}
	const end = Date.now() + 60000; let trust = false;
	while ((await ev('location.pathname')).startsWith('/sign-in')) {
		const body = await ev('document.body.innerText'); const href = await ev('location.href');
		if (!trust && (href.includes('client-trust') || /verification code|check your email|verify your email/i.test(body))) {
			trust = true; await ev(`document.querySelector('input').focus()`);
			for (const ch of '424242') { await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch }); await sleep(120); }
		}
		if (Date.now() > end) { await shot('signin_timeout'); throw new Error(`Clerk sign-in timeout: ${body.slice(0, 300).replace(/\s+/g, ' ')}`); } await sleep(400);
	}
	await goto('/app'); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000);
	return { signed_in: true, clerk_test: true, client_trust_code_used: trust };
}
function startPublisher(tag, count, extra = []) {
	const fd = openSync(`${LOGS}/${tag}.log`, 'w');
	// NHM_PRODUCER=ws drives the real network path (ESP32 emulator -> ingestion server -> Atlas); default writes to Atlas directly.
	const ws = process.env.NHM_PRODUCER === 'ws';
	const argv = ws ? ['-m', 'scripts.emulate_esp32_ws', '--url', process.env.NHM_WS_URL, '--timing', 'firmware', '--count', String(count), '--rate', '20', '--run-tag', tag, '--event-log', `${LOGS}/${tag}.events.jsonl`, '--summary-file', `${LOGS}/${tag}.summary.json`, ...extra]
		: ['-m', 'scripts.publish_hardware_test', '--count', String(count), '--rate', '20', '--run-tag', tag, ...extra];
	const childEnv = { ...process.env }; if (ws) delete childEnv.NHM_HARDWARE_MONGO_URI;  // the emulator never holds database credentials
	const child = spawn(process.env.NHM_TEST_PYTHON, argv, { cwd: process.cwd(), env: childEnv, stdio: ['ignore', fd, fd] });
	child.on('exit', () => closeFd(fd));
	let closed = false; function closeFd(n) { if (!closed) { closed = true; try { closeSync(n); } catch {} } }
	return child;
}
const waitExit = (child, timeout = 180000) => new Promise((resolve, reject) => { const timer = setTimeout(() => { child.kill('SIGTERM'); reject(new Error('publisher timeout')); }, timeout); child.on('exit', (code) => { clearTimeout(timer); code === 0 ? resolve(code) : reject(new Error(`publisher exit ${code}`)); }); });
async function openHardwareAndStart() {
	await goto('/app/monitoring'); await waitFor(`!!document.querySelector('#monitor-source')`); await setSelect('#monitor-source', 'hardware');
	await waitFor(`!!document.querySelector('[data-testid="hardware-start"]')`); await clickId('hardware-start'); await waitFor(`(${JSON.stringify(await value('hardware-state'))} !== 'x') && document.querySelector('[data-testid="hardware-state"]').textContent.includes('WAITING')`, 30000);
	return value('hardware-session-id');
}
async function monitorSnapshot() { return ev(`(() => { const text=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent??'').trim(); const svg=document.querySelector('[data-testid="hardware-waveform"]'); const latest=[...document.querySelectorAll('p')].find(p=>p.textContent.includes('Latest received: MongoDB ID')); const match=latest?.textContent.match(/MongoDB ID\\s+([0-9a-f]+)\\s+· ECG\\s+(\\d+)/i); const marker=svg?.querySelector('circle[fill="#fbbf24"]'); const ecg=match?Number(match[2]):null; return { state:text('hardware-state'), count:Number(text('hardware-record-count')), bpm:text('hardware-bpm'), spo2:text('hardware-spo2'), points:Number(svg?.getAttribute('data-points')??0), paths:Number(svg?.getAttribute('data-paths')??0), latest_id:match?.[1]??null, latest_ecg:ecg, latest_x:marker?Number(marker.getAttribute('cx')):null, latest_y:marker?Number(marker.getAttribute('cy')):null, expected_y:ecg===null?null:170-ecg/4095*150 }; })()`); }
async function runDemo(sessionId, rounds, algorithm) {
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
	await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-starter"]')`, 60000);
	await waitFor(`!!document.querySelector('[data-testid="hardware-demo-session-${sessionId}"]')`, 60000);
	await clickId(`rounds-${rounds}`);
	await clickId(`hardware-demo-session-${sessionId}`); await setSelect('[data-testid="hardware-demo-algorithm"]', algorithm); await setSelect('[data-testid="hardware-demo-secagg"]', 'SECAGG_SHADOW');
	await clickId('hardware-demo-start'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-result"]')`, 600000); const text = await value('hardware-demo-result'); await shot(`demo_${rounds}_${algorithm.toLowerCase()}`); return text;
}

const signin = await signIn(); const stamp = Date.now(); const out = { mode: MODE, signin, real_browser: true, real_clerk: true, actual_atlas: true, synthetic_source: true };
if (MODE === 'scenario-a') {
	const sid = await openHardwareAndStart(); const waiting = await monitorSnapshot(); await shot('a_waiting');
	const tag = `NHM-BROWSER-A-${stamp}`; const pub = startPublisher(tag, 1200, ['--initial-delay', '10', '--pause-at', '25', '--pause-duration', '7']);
	await waitFor(`Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 20`, 60000); const live = await monitorSnapshot(); await shot('a_live');
	await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('STALE')`, 60000); const stale = await monitorSnapshot(); await shot('a_stale');
	await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('LIVE')`, 30000); const recovered = await monitorSnapshot(); await shot('a_recovered');
	await waitExit(pub); await sleep(1500); const beforeStop = await monitorSnapshot(); await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000); const stopped = await monitorSnapshot(); await shot('a_stopped');
	await goto(`/app/history/${encodeURIComponent(sid)}`); await waitFor(`document.body.innerText.includes(${JSON.stringify(sid)}) && document.body.innerText.includes('actual accepted records')`, 60000); await shot('a_history');
	const fedavg = await runDemo(sid, 3, 'FEDAVG'); const fedprox = await runDemo(sid, 3, 'FEDPROX');
	Object.assign(out, { tag, session_id: sid, waiting, live, stale, recovered, before_stop: beforeStop, stopped, history_visible: true, demo_fl: { fedavg, fedprox } });
} else if (MODE === 'scenario-b') {
	let priorHistoryAfterRestart = null;
	if (process.env.NHM_EXPECT_SESSION) { await goto('/app/history'); await waitFor(`document.body.innerText.includes(${JSON.stringify(process.env.NHM_EXPECT_SESSION)})`, 60000); priorHistoryAfterRestart = true; await shot('b_prior_history_after_restart'); }
	const tag = `NHM-BROWSER-B-${stamp}`; const pub = startPublisher(tag, 2400); await sleep(18000);
	const sid1 = await openHardwareAndStart(); await sleep(60000); const firstLive = await monitorSnapshot(); await shot('b_first_live'); await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000); const firstStop = await monitorSnapshot();
	await sleep(4000); const firstStable = await monitorSnapshot(); await clickId('hardware-start'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('WAITING')`, 30000); const sid2 = await value('hardware-session-id'); await sleep(25000); const secondLive = await monitorSnapshot(); await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000); const secondStop = await monitorSnapshot(); await shot('b_second_stopped'); await waitExit(pub);
	await goto('/app/history'); await waitFor(`document.body.innerText.includes(${JSON.stringify(sid1)}) && document.body.innerText.includes(${JSON.stringify(sid2)})`, 60000); await shot('b_history');
	const fedavg = await runDemo(sid1, 10, 'FEDAVG'); const fedprox = await runDemo(sid1, 10, 'FEDPROX');
	Object.assign(out, { tag, prior_history_after_restart: priorHistoryAfterRestart, pre_emission_seconds: 18, first_session_id: sid1, first_live: firstLive, first_stop: firstStop, first_after_stop: firstStable, second_session_id: sid2, second_live: secondLive, second_stop: secondStop, separate_sessions: sid1 !== sid2, history_visible: true, demo_fl: { fedavg, fedprox } });
} else if (MODE === 'latency') {
	// First wall-clock moment each MongoDB _id is shown in the "Latest received" line (60 ms DOM sampling).
	const seconds = Number(process.env.NHM_LATENCY_SECONDS ?? 60); const tag = `NHM-BROWSER-LAT-${stamp}`;
	const sid = await openHardwareAndStart(); const pub = startPublisher(tag, Math.round(seconds * 20), []);
	const seen = {}; const t0 = Date.now(); const expr = `(() => { const p=[...document.querySelectorAll('p')].find(x=>x.textContent.includes('Latest received: MongoDB ID')); const m=p?p.textContent.match(/MongoDB ID\\s+([0-9a-f]{24})/i):null; return m?m[1]:null; })()`;
	while (Date.now() - t0 < seconds * 1000 + 4000) { const id = await ev(expr); if (id && !(id in seen)) seen[id] = Date.now(); await sleep(60); }
	await waitExit(pub, 60000).catch(() => {}); await clickId('hardware-stop');
	Object.assign(out, { tag, session_id: sid, seconds, seen, distinct_ids_displayed: Object.keys(seen).length });
} else if (MODE === 'soak') {
	// Long-running Monitor: sample JS heap, DOM size, plotted points and poll health while the emulator transmits continuously.
	const seconds = Number(process.env.NHM_SOAK_SECONDS ?? 600); const tag = `NHM-BROWSER-SOAK-${stamp}`;
	const sid = await openHardwareAndStart(); const pub = startPublisher(tag, Math.round(seconds * 20), []);
	const samples = []; const t0 = Date.now();
	while (Date.now() - t0 < seconds * 1000) {
		await sleep(30000);
		const snap = await monitorSnapshot();
		const mem = await ev(`({ heap: performance.memory ? performance.memory.usedJSHeapSize : null, nodes: document.getElementsByTagName('*').length, alert: !!document.querySelector('[role="alert"]') })`);
		samples.push({ t: Math.round((Date.now() - t0) / 1000), ...snap, ...mem });
		if (samples.length % 4 === 0) await shot(`soak_${samples.length}`);
	}
	await waitExit(pub, 120000).catch(() => {}); await sleep(2000); const beforeStop = await monitorSnapshot();
	await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000); const stopped = await monitorSnapshot();
	await goto(`/app/history/${encodeURIComponent(sid)}`); await waitFor(`document.body.innerText.includes(${JSON.stringify(sid)})`, 60000); await shot('soak_history');
	Object.assign(out, { tag, session_id: sid, seconds, samples, before_stop: beforeStop, stopped });
} else if (MODE === 'owner-probe') {
	const target = process.env.NHM_EXPECT_SESSION; if (!target) throw new Error('NHM_EXPECT_SESSION missing');
	await goto(`/app/history/${encodeURIComponent(target)}`); await waitFor(`document.querySelector('[role="alert"]') || document.body.innerText.includes('FORBIDDEN')`, 60000); const detailText = await ev('document.body.innerText'); await shot('owner_b_forbidden');
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
	await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-starter"]')`, 60000); await sleep(1000);
	Object.assign(out, { target_session: target, detail_refused: /forbidden|belongs to another user/i.test(detailText), target_absent_from_demo_sources: !(await ev(`document.body.innerText.includes(${JSON.stringify(target)})`)) });
} else throw new Error(`unknown mode ${MODE}`);
writeFileSync(OUT, JSON.stringify(out, null, 2)); await cdp.send('Browser.close').catch(() => {});
