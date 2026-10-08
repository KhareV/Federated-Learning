// OBS-DIAG-001 real-browser smoke: per-batch table after a real run with batch capture enabled, and the activation inspector.
//   node scripts/observatory_diag_smoke.mjs <debugPort> <origin> <outDir>      (stack must run with NHM_OBSERVATORY_BATCH_CAPTURE=1)
import { mkdirSync, writeFileSync } from 'node:fs';

const [, , debugPort, ORIGIN, OUT] = process.argv;
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp { constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = []; this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
	this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const { res, rej } = this.pending.get(e.id); this.pending.delete(e.id); e.error ? rej(new Error(JSON.stringify(e.error))) : res(e.result); } else if (e.method) for (const h of this.handlers) h(e.method, e.params); }; }
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); } }
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl); await cdp.ready;
const errors = [], hosts = new Set();
cdp.handlers.push((m, p) => { if (m === 'Runtime.exceptionThrown') errors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200)); if (m === 'Network.requestWillBeSent') { try { const u = new URL(p.request.url); if (u.protocol.startsWith('http')) hosts.add(u.hostname); } catch { /* data: */ } } });
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 200)); return r.result.value; }
async function waitFor(expression, timeout = 120000) { const until = Date.now() + timeout; while (Date.now() < until) { let v = null; try { v = await ev(expression); } catch { /* navigating */ } if (v) return v; await sleep(200); } throw new Error(`timeout: ${expression.slice(0, 100)}`); }
const viewport = async (w) => { await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: 1000, deviceScaleFactor: 1, mobile: w <= 480 }); await sleep(300); };
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(500); };
const shot = async (name) => { const r = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, 'base64')); };
await viewport(1440); await goto('/sign-in'); await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
await ev(`[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'ENTER DEMO WORKSPACE')?.click()`); await waitFor(`location.pathname === '/app'`);
// a real LIVE_RUN through the UI
await goto('/app/federation'); await waitFor(`document.body.innerText.includes('8 logical clients ready')`, 240000);
await ev(`document.querySelector('[data-testid="cfg-submit"]').click()`);
await waitFor(`location.pathname === '/app/federation/live'`, 60000);
await waitFor(`(document.querySelector('[data-testid="run-status"]')?.textContent ?? '').includes('COMPLETED')`, 300000);
const out = { steps: [] };
await goto('/app/observatory/federation'); await waitFor(`document.querySelectorAll('.roster button').length === 8`);
await waitFor(`!!document.querySelector('details.matrix') || document.body.innerText.includes('Selected client-round technical evidence')`);
await ev(`[...document.querySelectorAll('details')].filter((d) => d.textContent.includes('Selected client-round technical evidence')).forEach((d) => { d.open = true; })`); await sleep(800);
out.perBatch = await ev(`(() => { const t = document.querySelector('[data-testid="per-batch"] table'); return { present: !!t, rows: t ? t.querySelectorAll('tbody tr').length : 0, text: (document.querySelector('[data-testid="per-batch"] caption')?.textContent ?? '').slice(0, 90), exactSummaryNote: document.body.innerText.includes('reproduce the end-of-epoch summary exactly'), overflow: document.documentElement.scrollWidth > innerWidth }; })()`);
await shot('per_batch_1440');
await viewport(390); await sleep(400); out.perBatchMobileOverflow = await ev('document.documentElement.scrollWidth > innerWidth'); await shot('per_batch_390'); await viewport(1440);
await goto('/app/observatory/model'); await waitFor(`!!document.querySelector('[data-testid="activation-inspection"]')`);
await ev(`[...document.querySelectorAll('[data-testid="activation-inspection"] button')].find((b) => b.textContent.includes('Inspect'))?.click()`);
await waitFor(`!!document.querySelector('[data-testid="activation-parity"]')`, 90000);
out.activation = await ev(`(() => ({ parity: document.querySelector('[data-testid="activation-parity"]')?.textContent.includes('bit-identical'), heatmap: !!document.querySelector('[data-testid="activation-inspection"] svg rect'), cells: document.querySelectorAll('[data-testid="activation-inspection"] svg rect').length, hooksZero: document.querySelector('[data-testid="activation-parity"]')?.textContent.includes('hooks remaining after inspection: 0'), notExplanation: document.body.innerText.includes('NOT AN EXPLANATION METHOD'), overflow: document.documentElement.scrollWidth > innerWidth }))()`);
await shot('activation_1440'); await viewport(390); await sleep(400); out.activationMobileOverflow = await ev('document.documentElement.scrollWidth > innerWidth'); await shot('activation_390');
out.externalHosts = [...hosts].filter((h) => h !== '127.0.0.1' && h !== 'localhost'); out.errors = errors;
out.passed = out.perBatch.present && out.perBatch.rows === 2 && out.perBatch.exactSummaryNote && !out.perBatch.overflow && !out.perBatchMobileOverflow && out.activation.parity && out.activation.heatmap && out.activation.hooksZero && out.activation.notExplanation && !out.activation.overflow && !out.activationMobileOverflow && !out.externalHosts.length && !errors.length;
writeFileSync(`${OUT}/diag_smoke.json`, JSON.stringify(out, null, 1));
await cdp.send('Browser.close').catch(() => {});
console.log(JSON.stringify(out)); process.exit(out.passed ? 0 : 1);
