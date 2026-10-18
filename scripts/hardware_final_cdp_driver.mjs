// Real Chrome + real Clerk + real Atlas hardware-monitoring scenarios.
// Credentials are read from an ignored temporary file and never written to output.
import { readFileSync, writeFileSync, mkdirSync, openSync, closeSync, unlinkSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';
import { spawn } from 'node:child_process';

const [, , MODE, debugPort, ORIGIN, USERS, OUT, SHOTS, LOGS] = process.argv;
const user = JSON.parse(readFileSync(USERS))[process.env.NHM_BROWSER_USER ?? 'A'];
mkdirSync(SHOTS, { recursive: true }); mkdirSync(LOGS, { recursive: true });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const cdpEvents = [];
class Cdp {
	constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; }); this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const p = this.pending.get(e.id); this.pending.delete(e.id); e.error ? p.rej(new Error(JSON.stringify(e.error))) : p.res(e.result); } else if (e.method) { cdpEvents.push(e); if (cdpEvents.length > 400) cdpEvents.shift(); } }; }
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl); await cdp.ready;
for (const domain of ['Page', 'Runtime', 'Network', 'Log']) await cdp.send(`${domain}.enable`);
await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails)); return r.result.value; }
async function waitFor(expression, timeout = 120000) { const end = Date.now() + timeout; while (Date.now() < end) { try { const v = await ev(expression); if (v) return v; } catch {} await sleep(150); } try { await shot(`timeout_${Date.now()}`); writeFileSync(`${SHOTS}/timeout_page.txt`, await ev('location.pathname + "\\n" + document.body.innerText')); console.error('PAGE AT TIMEOUT: see timeout_page.txt'); } catch {} throw new Error(`timeout:${expression}`); }
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
function startPublisher(tag, count, extra = [], opts = {}) {
	const fd = openSync(`${LOGS}/${tag}.log`, 'w');
	// NHM_PRODUCER=ws drives the real network path (ESP32 emulator -> ingestion server -> Atlas); default writes to Atlas directly.
	const ws = process.env.NHM_PRODUCER === 'ws';
	const argv = ws ? ['-m', 'scripts.emulate_esp32_ws', '--url', process.env.NHM_WS_URL, '--timing', 'firmware', ...(opts.plan ? ['--plan', opts.plan] : ['--count', String(count), '--rate', '20']), ...(process.env.NHM_VITALS ? ['--vitals', process.env.NHM_VITALS] : []), '--run-tag', tag, ...(process.env.NHM_PATTERN ? ['--pattern', process.env.NHM_PATTERN] : []), '--event-log', `${LOGS}/${tag}.events.jsonl`, '--summary-file', `${LOGS}/${tag}.summary.json`, ...extra]
		: ['-m', 'scripts.publish_hardware_test', '--count', String(count), '--rate', '20', '--run-tag', tag, ...extra];
	const childEnv = { ...process.env }; if (ws) delete childEnv.NHM_HARDWARE_MONGO_URI;  // the emulator never holds database credentials
	const child = spawn(process.env.NHM_TEST_PYTHON, argv, { cwd: process.cwd(), env: childEnv, stdio: ['ignore', fd, fd] });
	child.startedAt = Date.now(); child.on('exit', () => { child.endedAt = Date.now(); closeFd(fd); });
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
async function runDemo(sessionId, rounds, algorithm, opts = {}) {
	// Merged "Start a federation run" form -> the SAME Live page every synthetic run uses.
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
	await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-starter"]')`, 60000);
	await waitFor(`!!document.querySelector('[data-testid="hardware-demo-session-${sessionId}"]')`, 60000);
	const initOptions = await ev(`[...document.querySelector('[data-testid="hardware-demo-init"]').options].map(o=>({value:o.value,label:o.textContent.trim(),disabled:o.disabled}))`);
	await clickId(`rounds-${rounds}`);
	await clickId(`hardware-demo-session-${sessionId}`); await setSelect('[data-testid="hardware-demo-init"]', opts.warm ? 'WARM_START' : 'FRESH_SEEDED'); await setSelect('[data-testid="hardware-demo-algorithm"]', algorithm); await setSelect('[data-testid="hardware-demo-secagg"]', opts.secagg ?? 'SECAGG_SHADOW');
	if (opts.warm) { await setSelect('[data-testid="hardware-demo-init"]', 'WARM_START'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-warm-run"]') && document.querySelector('[data-testid="hardware-demo-warm-run"]').options.length > 0`, 30000); }
	await shot(`form_${rounds}_${algorithm.toLowerCase()}${opts.warm ? '_warm' : ''}`);
	const v2Note = await value('hardware-demo-v2-note');
	await clickId('hardware-demo-start');
	await waitFor(`location.pathname === '/app/federation/live' && (new URLSearchParams(location.search).get('run') || '').startsWith('HDFLRUN-')`, 60000);
	const runId = await ev(`new URLSearchParams(location.search).get('run')`);
	await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 180000);
	await waitFor(`!!document.querySelector('[data-testid="metric-AUPRC"]') && !/NOT YET AVAILABLE|EVALUATING/.test(document.querySelector('[data-testid="metric-AUPRC"]').textContent) || false`, 60000).catch(() => {});
	await sleep(2500);
	const live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').trim();
		return { run_id: ${JSON.stringify('')} , status_line: t('run-status'), banner: (document.querySelector('[aria-label="Federation claims"]')?.textContent ?? '').trim().replace(/\\s+/g,' '),
		chips: [...document.querySelectorAll('.chips li')].map(x=>x.textContent.trim()), client_cards: document.querySelectorAll('[data-testid="client-grid"] li').length,
		card_tags: [...document.querySelectorAll('[data-testid="hardware-card-label"]')].length, hw_participation: t('hardware-participation').replace(/\\s+/g,' ').slice(0,400),
		hw_total_windows: t('hw-total-windows'), hw_raw_sent: t('hw-raw-sent'), metric_auprc: t('metric-AUPRC'), metric_accuracy: t('metric-accuracy'), metric_bce: t('metric-BCE'),
		metric_status: t('metric-status'), evaluated_graph_points: document.querySelectorAll('[data-testid^="fig-"] svg circle, .one svg circle').length,
		figure_avail: [...document.querySelectorAll('[data-availability]')].map(x=>x.getAttribute('data-availability')),
		final_state: t('hardware-final-state').slice(0,120), accepted_counter: t('accepted-counter'), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)),
		run_label_text: (document.body.innerText.match(/(\\d+)-round recorded-hardware run[^\\n]*/)||[''])[0], secagg: t('secagg-status') }; })()`);
	live.run_id = runId; live.init_options = initOptions; live.v2_note = v2Note;
	await shot(`live_${rounds}_${algorithm.toLowerCase()}${opts.warm ? '_warm' : ''}`);
	return live;
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
} else if (MODE === 'away') {
	// Lifecycle audit: Start -> readings -> leave Monitor for N s while the emitter continues -> return -> same session?
	const awayS = Number(process.env.NHM_AWAY_SECONDS ?? 15); const tag = `NHM-BROWSER-AWAY-${stamp}`;
	const sid = await openHardwareAndStart(); const pub = startPublisher(tag, Math.round(awayS * 17 + 60 * 17), []);
	await waitFor(`Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 40`, 60000);
	const beforeLeave = await monitorSnapshot(); await shot('away_1_before_leave');
	const apiState = async () => ev(`(async () => { const t = await (window.Clerk?.session?.getToken?.()); return null; })()`).catch(() => null);
	const leftAt = Date.now(); await goto('/app/history'); await waitFor(`document.body.innerText.includes(${JSON.stringify(sid)})`, 60000);
	const historyWhileAway = await ev(`document.body.innerText.includes('ACTIVE')`); await shot('away_2_history_while_away');
	await sleep(Math.max(0, awayS * 1000 - (Date.now() - leftAt)));
	const returnedAt = Date.now(); await goto('/app/monitoring'); await waitFor(`!!document.querySelector('#monitor-source')`); await setSelect('#monitor-source', 'hardware');
	await waitFor(`document.querySelector('[data-testid="hardware-session-id"]')?.textContent.trim() === ${JSON.stringify(sid)}`, 30000);
	const hasStartButton = await ev(`!!document.querySelector('[data-testid="hardware-start"]') && !document.querySelector('[data-testid="hardware-start"]').disabled`);
	const justReturned = await monitorSnapshot(); await shot('away_3_returned');
	await sleep(6000); const afterCatchUp = await monitorSnapshot(); await shot('away_4_caught_up');
	await waitExit(pub, 180000);
	// Stop once the count has stopped moving (the replica/Atlas insert backlog has drained): the replica inserts asynchronously and its lag varies with Atlas latency.
	{ let last = -1, stable = 0; while (stable < 3) { const c = Number(await value('hardware-record-count')); stable = c === last ? stable + 1 : 0; last = c; await sleep(1200); } }
	const beforeStop = await monitorSnapshot();
	const sidAfter = await value('hardware-session-id'); const lifecycleNote = await ev(`!!document.querySelector('[data-testid="hardware-lifecycle-note"]')`);
	await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000); const stopped = await monitorSnapshot(); await shot('away_5_stopped');
	await sleep(4000); const stoppedStable = await monitorSnapshot();
	await goto(`/app/history/${encodeURIComponent(sid)}`); await waitFor(`document.body.innerText.includes(${JSON.stringify(sid)}) && document.body.innerText.includes('actual accepted records')`, 60000); await shot('away_6_history');
	const historyText = await ev(`document.body.innerText`);
	const fedavg = await runDemo(sid, 3, 'FEDAVG');
	// Merged federation form: warm start from the run just completed (and check Pretrained V2 is shown as not applicable).
	const warm = await runDemo(sid, 3, 'FEDAVG', { warm: true });
	const initOptions = warm.init_options; const warmSource = warm.run_label_text; const warmText = JSON.stringify(warm); const v2Note = warm.v2_note;
	Object.assign(out, { tag, init_options: initOptions, warm_source_run: warmSource, warm_result: warmText, v2_note: v2Note, session_id: sid, session_id_after_return: sidAfter, away_seconds: awayS, left_at_ms: leftAt, returned_at_ms: returnedAt, before_leave: beforeLeave, history_shows_active_while_away: historyWhileAway, start_button_enabled_after_return: hasStartButton, just_returned: justReturned, after_catch_up: afterCatchUp, before_stop: beforeStop, stopped, stopped_stable: stoppedStable, lifecycle_note_visible: lifecycleNote, history_text_excerpt: historyText.slice(0, 1500), demo_fl: { fedavg } });
} else if (MODE === 'tour') {
	// Seed a recorded session and a completed hardware run, then tour every route (desktop + phone) including the hardware Live page.
	const tag = `NHM-BROWSER-TOUR-${stamp}`; const sid = await openHardwareAndStart(); const pub = startPublisher(tag, 700, []);
	await waitFor(`Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 500`, 120000);
	await waitExit(pub, 180000); await sleep(1500); await shot('tour_monitor_live');
	await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000);
	const run = await runDemo(sid, 3, 'FEDPROX', { secagg: 'SECAGG_SHADOW' });
	// Paired canonical synthetic run: the app's default 3-round LIVE run through the same starter, then the recorded historical FL10 evidence.
	let syntheticRun = null;
	try {
		if (process.env.NHM_TOUR_SYNTHETIC === '0') throw new Error('SKIPPED_BY_ENV');
		await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="cfg10-submit"], [data-testid="cfg-submit"]')`, 120000);
		const submit = await ev(`document.querySelector('[data-testid="cfg10-submit"]') ? 'cfg10-submit' : 'cfg-submit'`); await clickId(submit);
		await waitFor(`location.pathname === '/app/federation/live' && /^(FL10RUN|FEDRUN|[A-Z0-9-]+)/.test(new URLSearchParams(location.search).get('run') || '')`, 120000);
		syntheticRun = await ev(`new URLSearchParams(location.search).get('run')`);
		await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 1500000);
		await sleep(5000);
	} catch (error) { syntheticRun = { error: String(error).slice(0, 200), run: syntheticRun }; }
	const synRunId = typeof syntheticRun === 'string' ? syntheticRun : null;
	const { runTour } = await import('./ui_tour_lib.mjs');
	const report = await runTour({ cdp, ev, goto, events: cdpEvents, sleep, shots: SHOTS, out: `${OUT}.tour.json`,
		extraRoutes: [`/app/federation/live?run=${run.run_id}`, ...(synRunId ? [`/app/federation/live?run=${synRunId}`] : []), '/app/federation/live?run=recorded-A', `/app/history/${encodeURIComponent(sid)}`] });
	Object.assign(out, { tag, session_id: sid, hardware_run: run, synthetic_run: syntheticRun, routes_toured: report.length });
} else if (MODE === 'switch') {
	// RUN-SWITCH TRANSACTION in a real browser: hardware <-> recorded synthetic evidence through the run selector (SPA, no reload), browser back/forward and reload.
	const tag = `NHM-BROWSER-SWITCH-${stamp}`; const sid = await openHardwareAndStart(); const pub = startPublisher(tag, 600, []);
	await waitFor(`Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 450`, 120000);
	await waitExit(pub, 180000); await sleep(1500);
	await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000);
	const run = await runDemo(sid, 3, 'FEDAVG', { secagg: 'PLAIN' }); const HW = run.run_id;
	const READ = `(() => { const t = (id) => (document.querySelector('[data-testid="' + id + '"]')?.textContent ?? '').trim();
		return { url_run: new URLSearchParams(location.search).get('run'), selector: document.querySelector('[data-testid="run-selector"]')?.value ?? null, badge: t('source-badge'),
		banner: (document.querySelector('[aria-label="Federation claims"]')?.textContent ?? '').replace(/\\s+/g, ' ').trim(), chips: [...document.querySelectorAll('.chips li')].map((x) => x.textContent.trim()),
		clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map((x) => x.getAttribute('data-client')), hw_participation: !!document.querySelector('[data-testid="hardware-participation"]'),
		owner_label: !!document.querySelector('[data-testid="owner-card-label"]'), peer_labels: document.querySelectorAll('[data-testid="peer-label"]').length, status: t('run-status'),
		replay_note: !!document.querySelector('[data-testid="replay-note"]'), auprc: t('metric-AUPRC'), rounds_note: t('glance-status') }; })()`;
	const waitBadge = (b, run) => waitFor(`document.querySelector('[data-testid="source-badge"]')?.textContent.trim() === ${JSON.stringify(b)} && new URLSearchParams(location.search).get('run') === ${JSON.stringify(run)} && (document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 90000);
	const steps = [];
	const snap = async (name, expectBadge, expectRun) => { await waitBadge(expectBadge, expectRun); await sleep(2500); steps.push({ step: name, expected_run: expectRun, expected_badge: expectBadge, ...(await ev(READ)) }); };
	await goto(`/app/federation/live?run=${HW}`); await snap('open hardware', 'RECORDED HARDWARE', HW);
	await setSelect('[data-testid="run-selector"]', 'recorded-A'); await snap('switch to recorded synthetic evidence A (no reload)', 'RECORDED SYNTHETIC EVIDENCE', 'recorded-A');
	await setSelect('[data-testid="run-selector"]', HW); await snap('switch back to hardware (no reload)', 'RECORDED HARDWARE', HW);
	await setSelect('[data-testid="run-selector"]', 'recorded-B'); await snap('switch to recorded synthetic evidence B', 'RECORDED SYNTHETIC EVIDENCE', 'recorded-B');
	// Run selection uses replaceState by design (no history spam): Back leaves the page, Forward returns to the LAST selected run.
	await ev('history.back()'); await waitFor(`location.pathname === '/app/federation'`, 30000);
	steps.push({ step: 'browser back leaves the Live page (selection is replaceState)', expect_path: '/app/federation', ...(await ev(READ)), path: await ev('location.pathname') });
	await ev('history.forward()'); await snap('browser forward returns to the last selected run (recorded B)', 'RECORDED SYNTHETIC EVIDENCE', 'recorded-B');
	await ev('location.reload()'); await sleep(1500); await snap('reload keeps the selected run (recorded B)', 'RECORDED SYNTHETIC EVIDENCE', 'recorded-B');
	await setSelect('[data-testid="run-selector"]', HW); await snap('switch to hardware, then reload', 'RECORDED HARDWARE', HW);
	await ev('location.reload()'); await sleep(1500); await snap('reload on hardware', 'RECORDED HARDWARE', HW);
	await shot('switch_final_hardware');
	Object.assign(out, { tag, session_id: sid, hardware_run: HW, steps });
} else if (MODE === 'v2') {
	// Pretrained-V2 recorded-hardware path in a real browser: two retention-capped recordings (AD8232-amplitude emulator pattern through the local replica),
	// Observatory replay + window trace on the recorded session, the V2 starter's preview (single session refused, two accepted), a real V2 run and its generalisation tab.
	const tag = `NHM-BROWSER-V2-${stamp}`; const text = (id) => value(id);
	const record = async (n) => {
		const sid = await openHardwareAndStart(); const pub = startPublisher(`${tag}-${n}`, 2500, []);
		await waitFor(`Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 2000`, 240000);
		await waitExit(pub, 240000); await sleep(1500);
		await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000);
		return sid;
	};
	const sid1 = await record(1); const sid2 = await record(2); await shot('v2_monitor_stopped');
	const monitorReplayLink = await ev(`!!document.querySelector('[data-testid="hardware-monitor-replay"]')`);
	// --- History links
	await goto(`/app/history/${encodeURIComponent(sid1)}`); await waitFor(`!!document.querySelector('[data-testid="hardware-replay"]')`, 60000);
	const historyLinks = await ev(`({ replay: document.querySelector('[data-testid="hardware-replay"]')?.getAttribute('href'), trace: document.querySelector('[data-testid="hardware-trace"]')?.getAttribute('href') })`);
	// --- Session replay (hardware)
	cdpEvents.length = 0;
	await goto(`/app/observatory/replay?session=${encodeURIComponent(sid1)}`);
	await waitFor(`!!document.querySelector('[data-testid="replay-hardware-tag"]')`, 90000);
	await waitFor(`/scored/.test(document.querySelector('[data-testid="replay-hardware-summary"]')?.textContent ?? '') && !/pending/.test(document.querySelector('[data-testid="replay-hardware-summary"]')?.textContent ?? '') && !document.querySelector('[data-testid="replay-loading"]')`, 300000);
	await sleep(800);
	const replay = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
		return { tag: t('replay-hardware-tag'), summary: t('replay-hardware-summary'), has_controls: !!document.querySelector('[data-testid="replay-controls"]'), state: t('replay-state').slice(0, 500), transitions: t('replay-transitions').slice(0, 300),
		chart_points: document.querySelectorAll('[data-testid="replay-chart"] circle').length, selected: document.querySelector('.pick select')?.value ?? null, alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
	await shot('v2_replay');
	// --- Observatory signal trace (hardware)
	await goto(`/app/observatory?hw=${encodeURIComponent(sid1)}`);
	await waitFor(`!!document.querySelector('[data-testid="observatory-classification"]')`, 120000);
	await sleep(800);
	const trace = await ev(`(() => ({ classification: (document.querySelector('[data-testid="observatory-classification"]')?.textContent ?? '').trim(), stages: document.querySelectorAll('.signal-grid > *').length,
		summary: [...document.querySelectorAll('.summary > div')].map(x=>x.textContent.replace(/\\s+/g,' ').trim()), window_control: (document.querySelector('[data-testid="observatory-hardware-window"] output')?.textContent ?? '').trim(),
		inference: (document.querySelector('.inference h2')?.textContent ?? '').trim(), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }))()`);
	await shot('v2_trace');
	await ev(`document.querySelector('[data-testid="observatory-hardware-window"] .stepper button:last-of-type')?.click()`); await sleep(2500);
	const traceNext = await ev(`(document.querySelector('[data-testid="observatory-hardware-window"] output')?.textContent ?? '').trim()`);
	const consoleErrors = cdpEvents.flatMap((e) => e.method === 'Log.entryAdded' && e.params.entry.level === 'error' ? [`console:${String(e.params.entry.text).slice(0, 140)}:${String(e.params.entry.url ?? '').slice(0, 90)}`]
		: e.method === 'Network.responseReceived' && e.params.response.status >= 400 ? [`http ${e.params.response.status} ${String(e.params.response.url).replace(ORIGIN, '').slice(0, 120)}`]
		: e.method === 'Runtime.exceptionThrown' ? [`exception:${JSON.stringify(e.params.exceptionDetails.exception?.description ?? e.params.exceptionDetails.text).slice(0, 160)}`] : []);
	// --- Federation: V2 starter
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
	await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-starter"]')`, 60000);
	await waitFor(`!!document.querySelector('[data-testid="hardware-demo-session-${sid1}"]') && !!document.querySelector('[data-testid="hardware-demo-session-${sid2}"]')`, 60000);
	const initOptions = await ev(`[...document.querySelector('[data-testid="hardware-demo-init"]').options].map(o=>({value:o.value,disabled:o.disabled}))`);
	await clickId(`hardware-demo-session-${sid1}`); await setSelect('[data-testid="hardware-demo-init"]', 'MODEL_V2_FINAL');
	await waitFor(`!!document.querySelector('[data-testid="hardware-v2-preview"]')`, 120000);
	const single = await ev(`({ text: document.querySelector('[data-testid="hardware-v2-preview"]').textContent.replace(/\\s+/g,' ').trim().slice(0, 700), start_disabled: document.querySelector('[data-testid="hardware-demo-start"]').disabled })`);
	await shot('v2_form_single_refused');
	await clickId(`hardware-demo-session-${sid2}`);
	await waitFor(`/ENOUGH USABLE/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '') && !/NOT ENOUGH/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '')`, 180000);
	const both = await ev(`({ text: document.querySelector('[data-testid="hardware-v2-preview"]').textContent.replace(/\\s+/g,' ').trim().slice(0, 700), start_disabled: document.querySelector('[data-testid="hardware-demo-start"]').disabled })`);
	await setSelect('[data-testid="hardware-demo-algorithm"]', 'FEDPROX'); await setSelect('[data-testid="hardware-demo-secagg"]', 'SECAGG_SHADOW');
	await shot('v2_form_ready'); await clickId('hardware-demo-start');
	await waitFor(`location.pathname === '/app/federation/live' && (new URLSearchParams(location.search).get('run') || '').startsWith('HDFLRUN-')`, 120000);
	const runId = await ev(`new URLSearchParams(location.search).get('run')`);
	await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 900000);
	await sleep(4000);
	const live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
		return { status_line: t('run-status'), badge: t('source-badge'), clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map((x)=>x.getAttribute('data-client')), hw_participation: t('hardware-participation').slice(0, 500), recorded_cards: document.querySelectorAll('[data-testid="hardware-card-label"]').length, peer_cards: document.querySelectorAll('[data-testid="hardware-peer-label"]').length,
		metric_auprc: t('metric-AUPRC'), metric_accuracy: t('metric-accuracy'), secagg: t('secagg-status'), label: (document.body.innerText.match(/(\\d+)-round recorded-hardware run[^\\n]*/)||[''])[0],
		alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
	await shot('v2_live');
	await clickId('atab-generalisation'); await waitFor(`!!document.querySelector('[data-testid="generalisation-panel"]')`, 60000);
	await waitFor(`/rounds scored/.test(document.querySelector('[data-testid="generalisation-progress"]')?.textContent ?? '') || !!document.querySelector('[data-testid="generalisation-unavailable"]')`, 120000).catch(() => {});
	await waitFor(`(() => { const m = (document.querySelector('[data-testid="generalisation-progress"]')?.textContent ?? '').match(/(\\d+)\\/(\\d+) rounds scored/); return m && m[1] === m[2]; })()`, 900000).catch(() => {});
	const generalisation = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
		return { progress: t('generalisation-progress'), base_model: t('generalisation-base-model'), unavailable: t('generalisation-unavailable'), r0_identical: !!document.querySelector('[data-testid="generalisation-r0-identical"]') }; })()`);
	await shot('v2_generalisation');
	// --- Federation journal replay of the hardware run
	await goto('/app/observatory/federation-replay'); await waitFor(`!!document.querySelector('.pick select') && [...document.querySelector('.pick select').options].some(o=>o.value===${JSON.stringify(runId)})`, 60000);
	await setSelect('.pick select', runId); await waitFor(`!!document.querySelector('[data-testid="fed-replay-controls"]')`, 120000);
	await sleep(1500);
	const fedReplay = await ev(`({ option: [...document.querySelector('.pick select').options].find(o=>o.value===${JSON.stringify(runId)})?.textContent.trim(), clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map(x=>x.getAttribute('data-client')),
		jumps: [...document.querySelectorAll('[data-testid="fed-replay-controls"] button')].map(x=>x.textContent.trim()).filter(x=>/Jump to round/.test(x)), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) })`);
	await shot('v2_fed_replay');
	Object.assign(out, { tag, session_ids: [sid1, sid2], monitor_replay_link: monitorReplayLink, history_links: historyLinks, replay, trace, trace_next_window: traceNext, observatory_console_errors: consoleErrors,
		init_options: initOptions, single_session_preview: single, two_session_preview: both, run_id: runId, live, generalisation, fed_replay: fedReplay });
} else if (MODE === 'demo-session') {
	// The prerecorded DEMO hardware session (generated sketch-format documents in their own Mongo collection, imported as a STOPPED session): History, Observatory replay + trace, pretrained-V2 run and tabular run from that ONE session.
	const text = (id) => value(id);
	await goto('/app/history'); await waitFor(`[...document.querySelectorAll('code.sid')].some(x=>x.textContent.trim().startsWith('HW-SHOWCASE-'))`, 120000);
	const sid = await ev(`[...document.querySelectorAll('code.sid')].find(x=>x.textContent.trim().startsWith('HW-SHOWCASE-')).textContent.trim()`);
	const historyRow = await ev(`[...document.querySelectorAll('code.sid')].find(x=>x.textContent.trim().startsWith('HW-SHOWCASE-')).closest('tr').textContent.replace(/\\s+/g,' ').trim()`);
	await shot('demo_history');
	await goto(`/app/history/${encodeURIComponent(sid)}`); await waitFor(`!!document.querySelector('[data-testid="hardware-replay"]')`, 60000);
	const historyLinks = await ev(`({ replay: document.querySelector('[data-testid="hardware-replay"]')?.getAttribute('href'), trace: document.querySelector('[data-testid="hardware-trace"]')?.getAttribute('href'), page_text: document.body.innerText.replace(/\\s+/g,' ').slice(0, 900) })`);
	await waitFor(`!!document.querySelector('[data-testid="hardware-evidence-summary"]') && !document.querySelector('[data-testid="hardware-evidence-loading"]') && !!document.querySelector('[data-testid="hardware-window-results"]')`, 600000); await sleep(600);
	const evidence = await ev(`(() => { const t=(q)=>(document.querySelector(q)?.textContent ?? '').replace(/\\s+/g,' ').trim(); return { summary: t('[data-testid="hardware-evidence-summary"]'), states: [...document.querySelectorAll('[data-testid="hardware-evidence-states"] li')].map(x=>x.textContent.trim()), rows: document.querySelectorAll('[data-testid="hardware-window-results"] tbody tr').length, events: document.querySelectorAll('ol.events li').length, alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
	await shot('demo_history_detail');
	cdpEvents.length = 0;
	await goto(`/app/observatory/replay?session=${encodeURIComponent(sid)}`);
	await waitFor(`!!document.querySelector('[data-testid="replay-hardware-tag"]')`, 90000);
	await waitFor(`/scored/.test(document.querySelector('[data-testid="replay-hardware-summary"]')?.textContent ?? '') && !/pending/.test(document.querySelector('[data-testid="replay-hardware-summary"]')?.textContent ?? '') && !document.querySelector('[data-testid="replay-loading"]')`, 600000);
	await sleep(800);
	const replay = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
		return { tag: t('replay-hardware-tag'), summary: t('replay-hardware-summary'), has_controls: !!document.querySelector('[data-testid="replay-controls"]'), state: t('replay-state').slice(0, 500),
		chart_points: document.querySelectorAll('[data-testid="replay-chart"] circle').length, alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
	await shot('demo_replay');
	await goto(`/app/observatory?hw=${encodeURIComponent(sid)}`); await waitFor(`!!document.querySelector('[data-testid="observatory-classification"]')`, 120000); await sleep(800);
	const trace = await ev(`(() => ({ classification: (document.querySelector('[data-testid="observatory-classification"]')?.textContent ?? '').trim(), stages: document.querySelectorAll('.signal-grid > *').length, alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }))()`);
	await shot('demo_trace');
	const consoleErrors = cdpEvents.flatMap((e) => e.method === 'Log.entryAdded' && e.params.entry.level === 'error' ? [`console:${String(e.params.entry.text).slice(0, 140)}`]
		: e.method === 'Network.responseReceived' && e.params.response.status >= 400 ? [`http ${e.params.response.status} ${String(e.params.response.url).replace(ORIGIN, '').slice(0, 120)}`]
		: e.method === 'Runtime.exceptionThrown' ? [`exception:${JSON.stringify(e.params.exceptionDetails.exception?.description ?? e.params.exceptionDetails.text).slice(0, 160)}`] : []);
	// pretrained V2 from this single session
	const v2Runs = []; const tabularRuns = [];
	for (const rounds of (process.env.NHM_DEMO_ROUNDS ?? '3,10').split(',').map(Number)) {
		await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
		await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-session-${sid}"]')`, 60000);
		await clickId(`hardware-demo-session-${sid}`); await setSelect('[data-testid="hardware-demo-init"]', 'MODEL_V2_FINAL');
		await waitFor(`/ENOUGH USABLE/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '') && !/NOT ENOUGH/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '')`, 180000);
		const previewNow = await ev(`({ text: document.querySelector('[data-testid="hardware-v2-preview"]').textContent.replace(/\\s+/g,' ').trim().slice(0, 700), start_disabled: document.querySelector('[data-testid="hardware-demo-start"]').disabled })`);
		await clickId(`rounds-${rounds}`); await setSelect('[data-testid="hardware-demo-algorithm"]', 'FEDAVG'); await setSelect('[data-testid="hardware-demo-secagg"]', 'SECAGG_SHADOW'); await shot(`demo_v2_form_${rounds}`); await clickId('hardware-demo-start');
		await waitFor(`location.pathname === '/app/federation/live' && (new URLSearchParams(location.search).get('run') || '').startsWith('HDFLRUN-')`, 120000);
		const v2RunId = await ev(`new URLSearchParams(location.search).get('run')`);
		await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 900000);
		await waitFor(`/\\d\\.\\d/.test(document.querySelector('[data-testid="metric-AUPRC"]')?.textContent ?? '') && /\\d+ windows/.test(document.querySelector('[data-testid="metric-cohort"]')?.textContent ?? '')`, 900000).catch(() => {}); await sleep(2500);
		const v2Live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
			return { status_line: t('run-status'), badge: t('source-badge'), clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map((x)=>x.getAttribute('data-client')), recorded_cards: document.querySelectorAll('[data-testid="hardware-card-label"]').length, peer_cards: document.querySelectorAll('[data-testid="hardware-peer-label"]').length,
			metric_auprc: t('metric-AUPRC'), metric_cohort: t('metric-cohort'), glance_method: t('glance-method') || (document.querySelector('.cells')?.textContent ?? '').replace(/\\s+/g,' ').slice(0,300), candidate_panel: /FL10_CANDIDATE_HDFLRUN-/.test(document.body.innerText), backend_error: /Product backend error|BACKEND_ERROR/.test(document.body.innerText), chips: [...document.querySelectorAll('.chips li')].map(x=>x.textContent.trim()), final_state_panel: !!document.querySelector('[data-testid="hardware-final-state"]'), label: (document.body.innerText.match(/(\\d+)-round recorded-hardware run[^\\n]*/)||[''])[0], alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
		await shot(`demo_v2_live_${rounds}`);
		v2Runs.push({ rounds, preview: previewNow, run_id: v2RunId, live: v2Live });
		tabularRuns.push({ rounds, live: await runDemo(sid, rounds, 'FEDAVG') });
	}
	Object.assign(out, { session_id: sid, history_row: historyRow, history_links: historyLinks, evidence, replay, trace, observatory_console_errors: consoleErrors, v2_runs: v2Runs, tabular_runs: tabularRuns });
} else if (MODE === 'history-source') {
	// A COMPLETED simulated monitoring session from History as the signal of one federation client (synthetic-assigned labels), through the real starter.
	const clickText = (text) => ev(`(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(text)} && !x.disabled); if(!b) return false; b.click(); return true; })()`);
	await goto('/app/device'); await waitFor(`[...document.querySelectorAll('button')].some(x=>x.textContent.trim()==='ATTACH NHM VIRTUAL WEARABLE')`, 60000);
	await clickText('ATTACH NHM VIRTUAL WEARABLE'); await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim() === 'DETACHED'`, 30000);
	await waitFor(`[...document.querySelectorAll('button')].some(x=>x.textContent.trim()==='SCAN' && !x.disabled)`, 30000); await clickText('SCAN');
	await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim() === 'FOUND'`, 30000); await waitFor(`[...document.querySelectorAll('button')].some(x=>x.textContent.trim()==='PAIR / CONNECT' && !x.disabled)`, 30000); await clickText('PAIR / CONNECT');
	await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim() === 'CONNECTED'`, 30000);
	await goto('/app/monitoring'); await waitFor(`!!document.querySelector('[data-testid="create-session"]') && !document.querySelector('[data-testid="create-session"]').disabled`, 60000);
	await clickId('create-session'); await waitFor(`!!document.querySelector('[data-testid="start-session"]') && !document.querySelector('[data-testid="start-session"]').disabled`, 60000); await clickId('start-session');
	await goto('/app/history'); await waitFor(`!!document.querySelector('[data-testid="session-table"] code')`, 60000);
	let sessionId = '', state = ''; const t0 = Date.now();
	while (Date.now() - t0 < 300000) {
		await goto('/app/history'); await waitFor(`!!document.querySelector('[data-testid="session-table"] code')`, 60000);
		const row = await ev(`(() => { const tr = document.querySelector('[data-testid="session-table"] tbody tr'); return { id: tr.querySelector('code').textContent.trim(), text: tr.textContent }; })()`);
		sessionId = row.id; state = /COMPLETED/.test(row.text) ? 'COMPLETED' : /FAILED/.test(row.text) ? 'FAILED' : 'RUNNING';
		if (state !== 'RUNNING') break; await sleep(4000);
	}
	if (state !== 'COMPLETED') throw new Error('monitoring session ended ' + state);
	await goto('/app/history'); await waitFor(`document.body.innerText.includes(${JSON.stringify(sessionId)})`, 60000); await shot('hs_history');
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="rounds-10"]')`, 120000);
	await waitFor(`!!document.querySelector('[data-testid="cfg10-source"]') || !!document.querySelector('[data-testid="cfg10-submit"]')`, 60000);
	await waitFor(`!!document.querySelector('[data-testid="data-source-session"]') && !document.querySelector('[data-testid="data-source-session"]').disabled`, 60000); await clickId('data-source-session');
	await waitFor(`!!document.querySelector('[data-testid="cfg10-session"]') && [...document.querySelector('[data-testid="cfg10-session"]').options].some(o => o.value === ${JSON.stringify(sessionId)})`, 30000);
	await setSelect('[data-testid="cfg10-session"]', sessionId);
	const note = await value('cfg10-source-note'); await shot('hs_form');
	await clickId('cfg10-submit');
	await waitFor(`location.pathname === '/app/federation/live' && /^FL10RUN-/.test(new URLSearchParams(location.search).get('run') || '')`, 120000);
	const runId = await ev(`new URLSearchParams(location.search).get('run')`);
	await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 1200000);
	await sleep(4000);
	const live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
		return { badge: t('source-badge'), status_line: t('run-status'), clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map(x=>x.getAttribute('data-client')), metric_auprc: t('metric-AUPRC'), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)),
		local_examples: [...document.querySelectorAll('[data-testid="client-grid"] li')].map(x=>[x.getAttribute('data-client'), (x.textContent.match(/local examples: (\\S+)/)||[])[1]]) }; })()`);
	await shot('hs_live');
	await clickId('atab-overview').catch(() => {}); await sleep(1500);
	const overview = await ev(`(document.querySelector('[data-testid="monitoring-link"]')?.textContent ?? '').replace(/\\s+/g,' ').trim()`);
	await goto('/app/observatory/federation-replay'); await waitFor(`!!document.querySelector('.pick select') && [...document.querySelector('.pick select').options].some(o=>o.value===${JSON.stringify(runId)})`, 60000);
	await setSelect('.pick select', runId); await waitFor(`!!document.querySelector('[data-testid="fed-replay-controls"]') || !!document.querySelector('[role="alert"]')`, 180000);
	const replay = await ev(`({ controls: !!document.querySelector('[data-testid="fed-replay-controls"]'), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,200)) })`);
	await shot('hs_replay');
	Object.assign(out, { session_id: sessionId, run_id: runId, source_note: note, live, overview, replay });
} else if (MODE === 'realistic-cohort') {
	// The synthetic-cohort option, through the real starter: the original cohort is the default, REALISTIC is an explicit choice, and the run it starts is described, evaluated and labelled as realistic.
	const realisticRun = async (tag, monitoredSite) => {
		await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="cohort-realistic"]')`, 120000);
		await waitFor(`!!document.querySelector('[data-testid="cfg10-submit"]')`, 60000);
		const defaults = { original_checked: await attr('cohort-original', 'aria-checked'), realistic_checked: await attr('cohort-realistic', 'aria-checked'), submit_sent_cohort_text: await value('cfg10-cohort') };
		await clickId('cohort-realistic');
		const chosen = { realistic_checked: await attr('cohort-realistic', 'aria-checked'), note: await value('cohort-note'), fixed_cohort: await value('cfg10-cohort'), init: await ev(`document.querySelector('[data-testid="cfg10-init"]')?.value ?? null`) };
		if (monitoredSite !== undefined) { await setSelect('[data-testid="cfg10-source"]', 'LIVE_MONITORED_SITE_00'); await waitFor(`!!document.querySelector('[data-testid="cfg10-site"]')`, 30000); await setSelect('[data-testid="cfg10-site"]', String(monitoredSite)); }
		await shot(`rc_form_${tag}`);
		await clickId('cfg10-submit');
		await waitFor(`location.pathname === '/app/federation/live' && /^FL10RUN-/.test(new URLSearchParams(location.search).get('run') || '')`, 120000);
		const runId = await ev(`new URLSearchParams(location.search).get('run')`);
		await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 1500000);
		await waitFor(`!!document.querySelector('[data-testid="metric-AUPRC"]') && !/NOT YET AVAILABLE|EVALUATING|QUEUED/.test(document.querySelector('[data-testid="metric-AUPRC"]').textContent)`, 600000).catch(() => {});
		await sleep(4000);
		const live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
			return { badge: t('source-badge'), sentence: t('source-sentence'), status_line: t('run-status'), clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map(x=>x.getAttribute('data-client')),
			metric_auprc: t('metric-AUPRC'), metric_cohort: t('metric-cohort'), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)),
			body_has_realistic_use: /REALISTIC SYNTHETIC EVALUATION COHORT/.test(document.body.innerText), body_has_frozen_reuse: /REUSED SYNTHETIC DIAGNOSTIC EVALUATION/.test(document.body.innerText) }; })()`);
		await shot(`rc_live_${tag}`);
		await clickId('atab-overview').catch(() => {}); await sleep(1500);
		const overview = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim(); return { limits: t('limits'), monitoring_link: t('monitoring-link'), cards: t('overview-cards') }; })()`);
		await shot(`rc_overview_${tag}`);
		return { run_id: runId, defaults, chosen, live, overview };
	};
	out.canonical = await realisticRun('canonical');
	out.monitored = await realisticRun('monitored', 2);
} else if (MODE === 'candidate-library') {
	// Engineering candidates are kept when a run completes, listed on the Models page, and usable as the starting model of a later run (here across cohorts), through the real UI.
	const finishRun = async (tag) => {
		await waitFor(`location.pathname === '/app/federation/live' && /^FL10RUN-/.test(new URLSearchParams(location.search).get('run') || '')`, 120000);
		const runId = await ev(`new URLSearchParams(location.search).get('run')`);
		await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 1500000);
		await waitFor(`!!document.querySelector('[data-testid="metric-AUPRC"]') && !/NOT YET AVAILABLE|EVALUATING|QUEUED/.test(document.querySelector('[data-testid="metric-AUPRC"]').textContent)`, 600000).catch(() => {});
		await sleep(4000);
		const live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
			return { badge: t('source-badge'), status_line: t('run-status'), start_candidate: t('start-candidate'), metric_auprc: t('metric-AUPRC'), glance: t('run-at-a-glance'), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
		await shot(`cl_live_${tag}`);
		return { run_id: runId, live };
	};
	const libraryCards = () => ev(`[...document.querySelectorAll('[data-testid="library-candidates"] li[data-candidate]')].map((li) => ({ id: li.getAttribute('data-candidate'), cohort: li.getAttribute('data-cohort'), text: li.textContent.replace(/\\s+/g,' ').trim().slice(0, 600) }))`);
	// 1. a realistic run (3 rounds from the pretrained start)
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="cohort-realistic"]')`, 120000);
	await waitFor(`!!document.querySelector('[data-testid="cfg10-submit"]')`, 60000);
	await clickId('cohort-realistic'); await clickId('cfg10-submit');
	out.first = await finishRun('first');
	// 2. the candidate appears in the library (registered once every evaluation has settled): wait for it on the Models page
	let cards = [];
	for (let i = 0; i < 90 && !cards.length; i++) { await goto('/app/models'); await waitFor(`!!document.querySelector('[data-testid="candidate-library"]')`, 60000); await sleep(1500); cards = await libraryCards(); if (!cards.length) await sleep(4000); }
	await shot('cl_models'); out.models = { cards };
	// 3. start a second run from that candidate, on the ORIGINAL cohort (a cross-cohort start)
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="cfg10-init"]')`, 120000);
	await waitFor(`[...document.querySelector('[data-testid="cfg10-init"]').options].some((o) => o.value === 'CANDIDATE')`, 60000);
	await setSelect('[data-testid="cfg10-init"]', 'CANDIDATE'); await waitFor(`!!document.querySelector('[data-testid="cfg10-candidate"]')`, 30000);
	out.second_form = { note: await value('cfg10-candidate-note'), init_note: await value('cfg10-init-note'), options: await ev(`[...document.querySelector('[data-testid="cfg10-candidate"]').options].map((o) => o.value)`) };
	await shot('cl_form_second'); await clickId('cfg10-submit');
	out.second = await finishRun('second');
	// 4. the second run's own candidate joins the library, with the first as its parent
	let after = [];
	for (let i = 0; i < 90 && after.length < 2; i++) { await goto('/app/models'); await waitFor(`!!document.querySelector('[data-testid="candidate-library"]')`, 60000); await sleep(1500); after = await libraryCards(); if (after.length < 2) await sleep(4000); }
	await shot('cl_models_after'); out.models_after = { cards: after };
} else if (MODE === 'ui-shots') {
	// Visual review of the federation starter in every source-mode state (full page, desktop) plus the phone width.
	const clickText = (text) => ev(`(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(text)} && !x.disabled); if(!b) return false; b.click(); return true; })()`);
	await goto('/app/device'); await waitFor(`[...document.querySelectorAll('button')].some(x=>x.textContent.trim()==='ATTACH NHM VIRTUAL WEARABLE')`, 60000);
	await clickText('ATTACH NHM VIRTUAL WEARABLE'); await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim() === 'DETACHED'`, 30000);
	await waitFor(`[...document.querySelectorAll('button')].some(x=>x.textContent.trim()==='SCAN' && !x.disabled)`, 30000); await clickText('SCAN');
	await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim() === 'FOUND'`, 30000); await waitFor(`[...document.querySelectorAll('button')].some(x=>x.textContent.trim()==='PAIR / CONNECT' && !x.disabled)`, 30000); await clickText('PAIR / CONNECT');
	await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim() === 'CONNECTED'`, 30000);
	await goto('/app/monitoring'); await waitFor(`!!document.querySelector('[data-testid="create-session"]') && !document.querySelector('[data-testid="create-session"]').disabled`, 60000);
	await clickId('create-session'); await waitFor(`!!document.querySelector('[data-testid="start-session"]') && !document.querySelector('[data-testid="start-session"]').disabled`, 60000); await clickId('start-session');
	for (let i = 0; i < 80; i++) { await goto('/app/history'); await waitFor(`!!document.querySelector('[data-testid="session-table"] tbody tr')`, 60000); if (await ev(`/COMPLETED/.test(document.querySelector('[data-testid="session-table"] tbody tr').textContent)`)) break; await sleep(4000); }
	const full = async (name) => { const h = await ev('Math.max(document.documentElement.scrollHeight, 1000)'); await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: Math.min(h, 4000), deviceScaleFactor: 1, mobile: false }); await sleep(400); await shot(name); await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false }); };
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="rounds-10"]')`, 120000); await sleep(1500);
	await full('ui_01_default');
	await setSelect('[data-testid="cfg10-source"]', 'LIVE_MONITORED_SITE_00'); await sleep(600); await full('ui_02_live_site');
	await clickId('data-source-session'); await sleep(600); await full('ui_03_history_session');
	await clickId('rounds-10'); await sleep(600); await full('ui_04_ten_rounds');
	await cdp.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 900, deviceScaleFactor: 2, mobile: true }); await sleep(600);
	const h = await ev('document.documentElement.scrollHeight'); await cdp.send('Emulation.setDeviceMetricsOverride', { width: 390, height: Math.min(h, 4500), deviceScaleFactor: 1, mobile: true }); await sleep(500); await shot('ui_05_phone');
	await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
	Object.assign(out, { shots: 5 });
} else if (MODE === 'journey') {
	// Full simulated-hardware journey: sketch-faithful ESP32 emulator (mock BPM, ratio SpO2, AD8232-scale ECG, finger and lead removal) -> local Render replica -> Atlas rehearsal DB -> NHM:
	// live monitoring, recording, History, Observatory replay + trace, tabular hardware FL, then pretrained-V2 FL (and the high-gain negative case that the quality gate must refuse).
	const tag = `NHM-BROWSER-JOURNEY-${stamp}`;
	// HYPER-REALISTIC device model of the supplied sketch. Session A: boots with the electrodes not attached (leads off) while Render is still waking up (handshakes rejected for ~14 s, the sketch retries every 5 s),
	// then ECG with respiration/mains/motion artefacts, a finger removal, a leads-off stretch and a 9 s Wi-Fi drop. Session B: a calm 2 minute recording. Session C: a high-gain board (negative case).
	const PLAN = 'run:8:leadoff,run:45:sketch_real,unavail:7:sketch_real,run:25:sketch_real,run:6:leadoff,run:20:sketch_real,drop:9:sketch_real,run:25:sketch_real';
	const PLAN_B = 'run:125:sketch_real';
	const rejectFile = `${dirname(OUT)}/replica/REJECT_HANDSHAKES`;
	const quality = () => value('hardware-quality-state');
	const snap = async (name) => ({ name, ...(await monitorSnapshot()), quality: await quality(), v2: await value('hardware-v2-state'), v2_error: await value('hardware-v2-error') });
	const publishers = [];
	const record = async (n, plan, probes) => {
		const sid = await openHardwareAndStart();
		if (n === 'A') writeFileSync(rejectFile, '1');                 // Render is asleep: the replica refuses WebSocket handshakes (HTTP 503) until we wake it
		const pub = startPublisher(`${tag}-${n}`, 0, [], { plan }); publishers.push({ n, session_id: sid, pub });
		const snaps = [];
		if (n === 'A') { snaps.push({ name: 'render_asleep', ...(await monitorSnapshot()) }); await sleep(14000); if (existsSync(rejectFile)) unlinkSync(rejectFile); snaps.push({ name: 'render_woken_after_14s', ...(await monitorSnapshot()) }); }
		for (const [name, cond] of probes) { await waitFor(cond, 240000); snaps.push(await snap(name)); await shot(`j_${n}_${name}`); }       // condition probes: the emulator, replica and Atlas add start-up and insert lag
		await waitExit(pub, 400000);
		// A user stops once the count has stopped moving (the replica/Atlas insert backlog has drained), exactly as in real use.
		let last = -1, stable = 0; while (stable < 3) { const c = Number(await value('hardware-record-count')); stable = c === last ? stable + 1 : 0; last = c; await sleep(1200); }
		snaps.push(await snap('before_stop')); await shot(`j_${n}_before_stop`);
		await clickId('hardware-stop'); await waitFor(`document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('SESSION STOPPED')`, 30000); snaps.push(await snap('stopped'));
		return { sid, snaps, started_ms: pub.startedAt, ended_ms: pub.endedAt };
	};
	const bpmNow = `Number(document.querySelector('[data-testid="hardware-bpm"]')?.textContent) >= 72`;
	const A = await record('A', PLAN, [['live', `Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 300 && ${bpmNow}`],
		['finger_removed', `document.querySelector('[data-testid="hardware-bpm"]')?.textContent.trim() === 'Unavailable'`],
		['leads_off', `/ECG\\s+2048\\b/.test([...document.querySelectorAll('p')].find(p => p.textContent.includes('Latest received: MongoDB ID'))?.textContent ?? '')`],
		['wifi_dropped_stale', `document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('STALE')`],
		['recovered_live', `document.querySelector('[data-testid="hardware-state"]')?.textContent.includes('LIVE')`]]);
	const B = await record('B', PLAN_B, []);
	const C = await record('C', 'run:55:sketch_highgain', [['live_highgain', `Number(document.querySelector('[data-testid="hardware-record-count"]')?.textContent ?? 0) >= 400`]]);
	// --- History
	await goto('/app/history'); await waitFor(`[${[A, B, C].map((x) => JSON.stringify(x.sid)).join(',')}].every(id => document.body.innerText.includes(id))`, 60000); await shot('j_history');
	await goto(`/app/history/${encodeURIComponent(A.sid)}`); await waitFor(`document.body.innerText.includes('actual accepted records')`, 60000);
	const detail = await ev(`({ replay: !!document.querySelector('[data-testid="hardware-replay"]'), trace: !!document.querySelector('[data-testid="hardware-trace"]'), use_in_fl: !!document.querySelector('[data-testid="hardware-use-in-fl"]') })`); await shot('j_history_detail');
	// --- Observatory: session replay
	const replayOf = async (sid, name) => {
		cdpEvents.length = 0;
		await goto(`/app/observatory/replay?session=${encodeURIComponent(sid)}`); await waitFor(`!!document.querySelector('[data-testid="replay-hardware-tag"]')`, 90000);
		await waitFor(`(/scored/.test(document.querySelector('[data-testid="replay-hardware-summary"]')?.textContent ?? '') && !/pending/.test(document.querySelector('[data-testid="replay-hardware-summary"]')?.textContent ?? '') && !document.querySelector('[data-testid="replay-loading"]')) || !!document.querySelector('[data-testid="replay-empty"]')`, 400000);
		await sleep(800);
		const r = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
			return { summary: t('replay-hardware-summary'), empty: t('replay-empty'), controls: !!document.querySelector('[data-testid="replay-controls"]'), chart_points: document.querySelectorAll('[data-testid="replay-chart"] circle').length, state: t('replay-state').slice(0, 400), transitions: t('replay-transitions').slice(0, 400), alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
		await shot(`j_replay_${name}`);
		r.errors = cdpEvents.flatMap((e) => e.method === 'Log.entryAdded' && e.params.entry.level === 'error' ? [`console:${String(e.params.entry.text).slice(0, 120)}`] : e.method === 'Network.responseReceived' && e.params.response.status >= 400 ? [`http ${e.params.response.status} ${String(e.params.response.url).replace(ORIGIN, '').slice(0, 100)}`] : []);
		return r;
	};
	const replayA = await replayOf(A.sid, 'A'); const replayC = await replayOf(C.sid, 'C_highgain');
	// --- Observatory: window trace (a VALID window, then step to a rejected one)
	await goto(`/app/observatory?hw=${encodeURIComponent(A.sid)}`); await waitFor(`!!document.querySelector('[data-testid="observatory-classification"]')`, 120000); await sleep(800);
	const traceValid = await ev(`({ classification: (document.querySelector('[data-testid="observatory-classification"]')?.textContent ?? '').trim(), stages: document.querySelectorAll('.signal-grid > *').length, window: (document.querySelector('[data-testid="observatory-hardware-window"] output')?.textContent ?? '').trim(), inference: (document.querySelector('.inference h2')?.textContent ?? '').trim(), summary: [...document.querySelectorAll('.summary > div')].map(x=>x.textContent.replace(/\\s+/g,' ').trim()) })`);
	await shot('j_trace_valid');
	let traceBad = null;
	for (let i = 0; i < 30 && !traceBad; i++) {
		await ev(`document.querySelector('[data-testid="observatory-hardware-window"] .stepper button:last-of-type')?.click()`); await sleep(1800);
		const w = await ev(`(document.querySelector('[data-testid="observatory-hardware-window"] output')?.textContent ?? '')`);
		if (/UNUSABLE/.test(w)) { await sleep(1200); traceBad = await ev(`({ window: (document.querySelector('[data-testid="observatory-hardware-window"] output')?.textContent ?? '').trim(), quality: [...document.querySelectorAll('.summary > div')].map(x=>x.textContent.replace(/\\s+/g,' ').trim()), none: (document.querySelector('.not-available')?.textContent ?? '').trim(), has_inference: !!document.querySelector('.inference') })`); await shot('j_trace_rejected'); }
	}
	// --- Hardware FL, tabular model (safe path): FedAvg on A, FedProx + SecAgg shadow on B
	const tabA = await runDemo(A.sid, 3, 'FEDAVG', { secagg: 'PLAIN' });
	const tabB = await runDemo(B.sid, 3, 'FEDPROX', { secagg: 'SECAGG_SHADOW' });
	// --- Pretrained V2: the high-gain recording must be refused with the reason; the good recordings train
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
	await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-starter"]')`, 60000);
	await waitFor(`[${[A, B, C].map((x) => JSON.stringify(`[data-testid="hardware-demo-session-${x.sid}"]`)).join(',')}].every(q => !!document.querySelector(q))`, 60000);
	await setSelect('[data-testid="hardware-demo-init"]', 'MODEL_V2_FINAL');
	await clickId(`hardware-demo-session-${C.sid}`); await waitFor(`!!document.querySelector('[data-testid="hardware-v2-preview"]')`, 180000);
	await waitFor(`/NOT ENOUGH/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '') || /ENOUGH/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '')`, 180000);
	const previewC = await ev(`({ text: document.querySelector('[data-testid="hardware-v2-preview"]').textContent.replace(/\\s+/g,' ').trim().slice(0, 900), start_disabled: document.querySelector('[data-testid="hardware-demo-start"]').disabled })`); await shot('j_v2_refused_highgain');
	await clickId(`hardware-demo-session-${C.sid}`); await clickId(`hardware-demo-session-${A.sid}`); await clickId(`hardware-demo-session-${B.sid}`);
	await waitFor(`/ENOUGH USABLE/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '') && !/NOT ENOUGH/.test(document.querySelector('[data-testid="hardware-v2-preview"]')?.textContent ?? '')`, 240000);
	const previewAB = await ev(`({ text: document.querySelector('[data-testid="hardware-v2-preview"]').textContent.replace(/\\s+/g,' ').trim().slice(0, 600), start_disabled: document.querySelector('[data-testid="hardware-demo-start"]').disabled })`);
	await clickId('hardware-demo-start');
	await waitFor(`location.pathname === '/app/federation/live' && (new URLSearchParams(location.search).get('run') || '').startsWith('HDFLRUN-')`, 180000);
	const v2Run = await ev(`new URLSearchParams(location.search).get('run')`);
	await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent || '').includes('COMPLETED')`, 900000); await sleep(4000);
	const v2Live = await ev(`(() => { const t=(id)=>(document.querySelector('[data-testid="'+id+'"]')?.textContent ?? '').replace(/\\s+/g,' ').trim();
		return { badge: t('source-badge'), clients: [...document.querySelectorAll('[data-testid="client-grid"] li')].map(x=>x.getAttribute('data-client')), metric_auprc: t('metric-AUPRC'), label: (document.body.innerText.match(/(\\d+)-round recorded-hardware run[^\\n]*/)||[''])[0], alerts: [...document.querySelectorAll('[role="alert"]')].map(x=>x.textContent.trim().slice(0,160)) }; })()`);
	await shot('j_v2_live');
	await clickId('atab-generalisation'); await waitFor(`!!document.querySelector('[data-testid="generalisation-panel"]')`, 60000);
	await waitFor(`(() => { const m = (document.querySelector('[data-testid="generalisation-progress"]')?.textContent ?? '').match(/(\\d+)\\/(\\d+) rounds scored/); return m && m[1] === m[2]; })()`, 900000).catch(() => {});
	const gen = await value('generalisation-progress');
	Object.assign(out, { tag, plan: PLAN, plan_b: PLAN_B, sessions: { A, B, C: { ...C } }, detail, replay: { A: replayA, C: replayC }, trace: { valid: traceValid, rejected: traceBad }, tabular: { A: tabA, B: tabB }, v2: { preview_c: previewC, preview_ab: previewAB, run_id: v2Run, live: v2Live, generalisation: gen } });
} else if (MODE === 'owner-probe') {
	const target = process.env.NHM_EXPECT_SESSION; if (!target) throw new Error('NHM_EXPECT_SESSION missing');
	await goto(`/app/history/${encodeURIComponent(target)}`); await waitFor(`document.querySelector('[role="alert"]') || document.body.innerText.includes('FORBIDDEN')`, 60000); const detailText = await ev('document.body.innerText'); await shot('owner_b_forbidden');
	await goto('/app/federation'); await waitFor(`!!document.querySelector('[data-testid="data-source-hardware"]')`, 120000);
	await clickId('data-source-hardware'); await waitFor(`!!document.querySelector('[data-testid="hardware-demo-starter"]')`, 60000); await sleep(1000);
	Object.assign(out, { target_session: target, detail_refused: /forbidden|belongs to another user/i.test(detailText), target_absent_from_demo_sources: !(await ev(`document.body.innerText.includes(${JSON.stringify(target)})`)) });
} else throw new Error(`unknown mode ${MODE}`);
writeFileSync(OUT, JSON.stringify(out, null, 2)); await cdp.send('Browser.close').catch(() => {});
