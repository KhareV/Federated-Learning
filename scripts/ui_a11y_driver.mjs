// Real Chrome + real Clerk test user: accessibility / semantics / console / network audit of every product route. No hardware, no data seeding.
import { readFileSync, mkdirSync } from 'node:fs';
import { runA11y, ROUTES } from './ui_a11y_lib.mjs';

const [, , debugPort, ORIGIN, USERS, OUT] = process.argv;
const user = JSON.parse(readFileSync(USERS))[process.env.NHM_BROWSER_USER ?? 'A'];
const events = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp {
	constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
		this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const p = this.pending.get(e.id); this.pending.delete(e.id); e.error ? p.rej(new Error(JSON.stringify(e.error))) : p.res(e.result); } else if (e.method) { events.push(e); if (events.length > 2500) events.shift(); } }; }
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl); await cdp.ready;
for (const d of ['Page', 'Runtime', 'Network', 'Log']) await cdp.send(`${d}.enable`);
const ev = async (expression) => { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 240)); return r.result.value; };
async function waitFor(expression, timeout = 60000) { const end = Date.now() + timeout; while (Date.now() < end) { try { const v = await ev(expression); if (v) return v; } catch {} await sleep(150); } throw new Error(`timeout:${expression.slice(0, 70)}`); }
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(500); };
async function signIn() {
	await goto('/sign-in'); await waitFor(`!!document.querySelector('input[name=identifier]')`, 60000);
	await ev(`document.querySelector('input[name=identifier]').focus()`); await cdp.send('Input.insertText', { text: user.email }); await sleep(400);
	await ev(`([...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue')).click()`); await waitFor(`!!document.querySelector('input[name=password]')`, 30000);
	await sleep(1500); await ev(`document.querySelector('input[name=password]').focus()`); await cdp.send('Input.insertText', { text: user.password }); await sleep(600);
	await ev(`([...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue')).click()`); await sleep(4000);
	if ((await ev('location.pathname')).startsWith('/sign-in') && /Enter your password/.test(await ev('document.body.innerText'))) await ev(`([...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Continue')).click()`);
	const end = Date.now() + 60000; let trust = false;
	while ((await ev('location.pathname')).startsWith('/sign-in')) {
		const body = await ev('document.body.innerText'); const href = await ev('location.href');
		if (!trust && (href.includes('client-trust') || /verification code|check your email|verify your email/i.test(body))) { trust = true; await ev(`document.querySelector('input').focus()`); for (const ch of '424242') { await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: ch, text: ch }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch }); await sleep(120); } }
		if (Date.now() > end) throw new Error('Clerk sign-in timeout'); await sleep(400);
	}
	await goto('/app'); await waitFor(`!!document.querySelector('[data-testid="identity-chip"]')`, 60000);
}
await signIn();
const only = process.env.NHM_A11Y_VIEWPORTS ? process.env.NHM_A11Y_VIEWPORTS.split(',') : ['desktop', 'phone'];
const ALL = { desktop: { name: 'desktop', width: 1440, height: 900, mobile: false }, laptop: { name: 'laptop', width: 1024, height: 768, mobile: false }, tablet: { name: 'tablet', width: 768, height: 1024, mobile: true }, phone: { name: 'phone', width: 390, height: 844, mobile: true } };
const routes = process.env.NHM_A11Y_ROUTES ? JSON.parse(process.env.NHM_A11Y_ROUTES) : ROUTES;
await runA11y({ cdp, ev, goto, events, sleep, out: OUT, routes, viewports: only.map((v) => ALL[v]), tabMax: Number(process.env.NHM_A11Y_TABMAX ?? 90) });
await new Promise((r) => setTimeout(r, 50)); process.exit(0);
