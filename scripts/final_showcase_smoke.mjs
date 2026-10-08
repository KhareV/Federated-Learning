// NHM-FINAL-SHOWCASE-001 real-browser smoke: outcomes dashboard (selectors, evolution, comparability, synthetic label), storyboard with a real opt-in live link, mobile overflow.
//   node scripts/final_showcase_smoke.mjs <debugPort> <origin> <outDir>
import { mkdirSync, writeFileSync } from 'node:fs';

const [, , debugPort, ORIGIN, OUT] = process.argv;
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp { constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = []; this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
	this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const { res, rej } = this.pending.get(e.id); this.pending.delete(e.id); e.error ? rej(new Error(JSON.stringify(e.error))) : res(e.result); } else if (e.method) for (const h of this.handlers) h(e.method, e.params); };}
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); } }
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl); await cdp.ready;
const errors = [], hosts = new Set();
cdp.handlers.push((m, p) => { if (m === 'Runtime.exceptionThrown') errors.push(String(p.exceptionDetails?.exception?.description ?? p.exceptionDetails?.text).slice(0, 200)); if (m === 'Network.requestWillBeSent') { try { const u = new URL(p.request.url); if (u.protocol.startsWith('http')) hosts.add(u.hostname); } catch { /* ignore */ } } });
for (const d of ['Page', 'Runtime', 'Network']) await cdp.send(`${d}.enable`);
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 200)); return r.result.value; }
async function waitFor(expression, timeout = 60000) { const until = Date.now() + timeout; while (Date.now() < until) { let v = null; try { v = await ev(expression); } catch { /* navigating */ } if (v) return v; await sleep(200); } throw new Error(`timeout: ${expression.slice(0, 100)}`); }
const viewport = async (w) => { await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: 1000, deviceScaleFactor: 1, mobile: w <= 480 }); await sleep(300); };
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(500); };
const shot = async (name) => { const r = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, 'base64')); };
const setSelect = (label, value) => ev(`(() => { const s = [...document.querySelectorAll('label')].find((l) => l.textContent.trim().startsWith(${JSON.stringify(label)}))?.querySelector('select'); if (!s) return false; s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
await viewport(1440); await goto('/sign-in'); await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
await ev(`[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'ENTER DEMO WORKSPACE')?.click()`); await waitFor(`location.pathname === '/app'`);
const out = {};
await goto('/app/observatory/outcomes'); await waitFor(`!!document.querySelector('[data-testid="comparability-matrix"]')`);
out.outcomes = await ev(`(() => ({ matrixRows: document.querySelectorAll('[data-testid="comparability-matrix"] tbody tr').length, interpretations: document.querySelectorAll('[data-testid="interpretations"] li').length,
	label: document.querySelector('[data-testid="synthetic-label"]')?.textContent ?? '', frozen: document.querySelector('[data-testid="frozen-label"]')?.textContent ?? '', evolutionPath: !!document.querySelector('[data-testid="training-evolution"] path.line'),
	noSuperiority: document.body.innerText.includes('NO SUPERIORITY') }))()`);
const before = await ev(`document.querySelector('[data-testid="training-evolution"] path.line')?.getAttribute('d')`);
await setSelect('Condition', 'label'); await sleep(500);
const after = await ev(`document.querySelector('[data-testid="training-evolution"] path.line')?.getAttribute('d')`);
out.selectorChangesEvolution = !!before && !!after && before !== after;
await setSelect('Algorithm', 'FedProx'); await sleep(400);
out.fedproxRows = await ev(`document.querySelectorAll('[data-testid="outcome-models"] tbody tr').length`);
await shot('outcomes_1440'); await viewport(390); await sleep(400); out.outcomesMobileOverflow = await ev('document.documentElement.scrollWidth > innerWidth'); await shot('outcomes_390'); await viewport(1440);
await goto('/app/observatory/storyboard'); await waitFor(`!!document.querySelector('[data-testid="storyboard-step"]')`);
out.steps = [];
for (let i = 0; i < 8; i++) {
	out.steps.push(await ev(`({ lane: document.querySelector('[data-testid="lane-label"]')?.textContent, title: document.querySelector('[data-testid="storyboard-step"] h2')?.textContent })`));
	if (i < 7) await ev(`[...document.querySelectorAll('.nav button')].find((b) => b.textContent.includes('Next'))?.click()`);
	await sleep(120);
}
out.recordedShown = await ev(`document.querySelector('[data-testid="live-phase"]')?.textContent ?? ''`);
await ev(`[...document.querySelectorAll('[data-testid="live-link"] button')].find((b) => b.textContent.includes('Start live-monitored'))?.click()`);
await waitFor(`(document.querySelector('[data-testid="live-phase"]')?.textContent ?? '').includes('This session') && /phase (COMPLETED|BLOCKED)/.test(document.querySelector('[data-testid="live-phase"]').textContent)`, 420000);
out.live = await ev(`(() => ({ phase: document.querySelector('[data-testid="live-phase"]').textContent, parity: document.querySelector('[data-testid="live-parity"]')?.textContent ?? '', blocked: document.querySelector('[data-testid="live-blocked"]')?.textContent ?? '', card: document.querySelector('[data-testid="live-link"]').textContent.slice(-420) }))()`);
await shot('storyboard_1440'); await viewport(390); await sleep(400); out.storyboardMobileOverflow = await ev('document.documentElement.scrollWidth > innerWidth'); await shot('storyboard_390');
out.externalHosts = [...hosts].filter((h) => h !== '127.0.0.1' && h !== 'localhost'); out.errors = errors;
out.passed = out.outcomes.matrixRows === 2 && out.outcomes.interpretations === 4 && out.outcomes.label.startsWith('SYNTHETIC ENGINEERING-EVENT CLASSIFICATION') && out.outcomes.evolutionPath && out.outcomes.noSuperiority
	&& out.selectorChangesEvolution && out.fedproxRows > 0 && !out.outcomesMobileOverflow && !out.storyboardMobileOverflow && out.steps.length === 8 && out.steps.every((s) => /^[ABCH] ·/.test(s.lane ?? ''))
	&& /phase COMPLETED/.test(out.live.phase) && out.live.parity.includes('yes') && out.externalHosts.length === 0 && out.errors.length === 0;
writeFileSync(`${OUT}/final_showcase_smoke.json`, JSON.stringify(out, null, 1));
await cdp.send('Browser.close').catch(() => {});
console.log(JSON.stringify(out)); process.exit(out.passed ? 0 : 1);
