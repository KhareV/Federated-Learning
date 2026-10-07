// Real-Chrome, offline product UI sweep. No mocked product responses.
// node scripts/ui_enh_003_browser.mjs <debugPort> <origin> <outputDir> <stage>
import { mkdirSync, writeFileSync } from 'node:fs';
const [, , debugPort, origin, outDir, stage] = process.argv;
mkdirSync(outDir, { recursive: true });
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
class Cdp {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = [];
    this.ready = new Promise((yes, no) => { this.ws.onopen = yes; this.ws.onerror = no; });
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { yes, no } = this.pending.get(msg.id); this.pending.delete(msg.id);
        msg.error ? no(new Error(JSON.stringify(msg.error))) : yes(msg.result);
      } else if (msg.method) for (const fn of this.handlers) fn(msg.method, msg.params);
    };
  }
  send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((yes, no) => this.pending.set(id, { yes, no })); }
  on(fn) { this.handlers.push(fn); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const hosts = new Set(), errors = [], networkFailures = [];
cdp.on((method, params) => {
  if (method === 'Network.requestWillBeSent') { try { hosts.add(new URL(params.request.url).hostname); } catch {} }
  if (method === 'Network.loadingFailed' && !params.canceled) networkFailures.push(params.errorText);
  if (method === 'Runtime.exceptionThrown') errors.push(String(params.exceptionDetails?.exception?.description ?? params.exceptionDetails?.text));
  if (method === 'Runtime.consoleAPICalled' && params.type === 'error') errors.push(params.args.map((a) => a.value ?? a.description).join(' '));
});
for (const domain of ['Page', 'Runtime', 'Network']) await cdp.send(`${domain}.enable`);
const evalJs = async (expression) => {
  const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(`Browser evaluation failed: ${expression.slice(0, 80)}`);
  return r.result.value;
};
const waitFor = async (expression, timeout = 60000) => {
  const until = Date.now() + timeout;
  while (Date.now() < until) { try { if (await evalJs(expression)) return; } catch {} await sleep(100); }
  throw new Error(`Timed out: ${expression.slice(0, 110)}`);
};
const goto = async (path) => { await cdp.send('Page.navigate', { url: origin + path }); await sleep(250); await waitFor(`!!document.querySelector('main h1')`); };
const viewport = (width) => cdp.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width <= 768 });
const click = (label) => evalJs(`(()=>{const e=[...document.querySelectorAll('button,a')].find(x=>x.textContent.trim()===${JSON.stringify(label)});if(!e||e.disabled)return false;e.click();return true})()`);
const clickId = (id) => evalJs(`(()=>{const e=document.querySelector('[data-testid=${JSON.stringify(id)}]');if(!e||e.disabled)return false;e.click();return true})()`);
const facts = () => evalJs(`(()=>({h1:[...document.querySelectorAll('main h1')].map(x=>x.textContent.trim()),scrollWidth:document.documentElement.scrollWidth,width:innerWidth,body:document.body.innerText,focusable:[...document.querySelectorAll('main a,main button,main select,main summary')].filter(x=>!x.disabled).length}))()`);
const shot = async (name) => { const r = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(`${outDir}/${name}.png`, Buffer.from(r.data, 'base64')); };
await viewport(1440); await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
if (!await click('ENTER DEMO WORKSPACE')) throw new Error('Demo entry unavailable');
await waitFor(`location.pathname==='/app' && !!document.querySelector('[data-testid="demo-banner"]')`);

// Genuine product journey, including persisted history detail.
await goto('/app/device');
await waitFor(`document.body.innerText.includes('ATTACH NHM VIRTUAL WEARABLE')`);
if (!await click('ATTACH NHM VIRTUAL WEARABLE')) throw new Error('Attach unavailable');
await waitFor(`!!document.querySelector('[data-testid="device-state"]')`);
if (!await click('SCAN')) throw new Error('Scan unavailable');
await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim()==='FOUND'`);
if (!await click('PAIR / CONNECT')) throw new Error('Connect unavailable');
await waitFor(`document.querySelector('[data-testid="device-state"]')?.textContent.trim()==='CONNECTED'`);
await goto('/app/monitoring');
await waitFor(`!!document.querySelector('[data-testid="create-session"]')`);
if (!await clickId('create-session')) throw new Error('Create session unavailable');
await waitFor(`document.querySelector('[data-testid="session-state"]')?.textContent.trim()==='DEVICE_READY'`);
const sessionId = await evalJs(`document.querySelector('[data-testid="session-id"]')?.textContent.trim()`);
await waitFor(`document.querySelector('[data-testid="stream-status"]')?.textContent.includes('OPEN')`, 30000);
if (!await clickId('start-session')) throw new Error('Start session unavailable');
await waitFor(`!!document.querySelector('[data-testid="session-complete"]')`, 170000);
const monitoring = await evalJs(`(()=>({state:document.querySelector('[data-testid="session-state"]')?.textContent.trim(),model:document.querySelector('[data-testid="inf-model"]')?.textContent.trim(),calibration:document.querySelector('[data-testid="inf-cal"]')?.textContent.trim()}))()`);
const historyPath = `/app/history/${encodeURIComponent(sessionId)}`;
await goto(historyPath); await waitFor(`document.body.innerText.includes('Persisted session summary')`);

const pages = [
  ['overview','/app'],['device','/app/device'],['monitoring','/app/monitoring'],['history','/app/history'],
  ['history_detail',historyPath],['federation','/app/federation'],['federation_live','/app/federation/live'],
  ['federation_clients','/app/federation/clients'],['federation_rounds','/app/federation/rounds'],
  ['federation_privacy','/app/federation/privacy'],['models','/app/models'],
  ['research_ml','/app/research/ml'],['research_fl','/app/research/fl'],['system','/app/system'],['about','/app/about']
];
const highDensity = new Set(['overview','device','monitoring','history','history_detail','federation','federation_live','federation_clients','federation_rounds','models','research_ml','research_fl']);
const records = [];
for (const [name, path] of pages) {
  const widths = {};
  for (const width of (highDensity.has(name) ? [1440,1024,768,390] : [1440,390])) {
    await viewport(width); await goto(path);
    if (name.startsWith('research_')) await waitFor(`!!document.querySelector('[data-testid="full-frozen-evidence"]')`);
    if (name === 'history') await waitFor(`document.body.innerText.includes(${JSON.stringify(sessionId)})`);
    if (name === 'history_detail') await waitFor(`document.body.innerText.includes('Persisted session summary')`);
    await sleep(250);
    const f = await facts();
    widths[width] = { overflow: f.scrollWidth > f.width + 1, h1: f.h1, focusable: f.focusable, bodyExcerpt: f.body.slice(0, 500) };
    if (stage === 'final' && (width === 1440 || width === 390)) await shot(`${name}_${width}`);
  }
  records.push({ name, path, widths });
}
await viewport(1440); await goto('/app/federation');
const formLabelsSeparated = await evalJs(`(()=>{const labels=[...document.querySelectorAll('form[aria-label="Federation run configuration"] label')];return labels.length===3&&labels.every(label=>{const caption=label.querySelector('span'),select=label.querySelector('select');return caption&&select&&caption.getBoundingClientRect().bottom<=select.getBoundingClientRect().top+1})})()`);
await goto('/app/history');
await waitFor(`document.body.innerText.includes(${JSON.stringify(sessionId)})`);
const historyEvidenceVisible = await evalJs(`(()=>{const a=document.querySelector('[data-testid="session-table"] a');return !!a&&a.getBoundingClientRect().right<=innerWidth&&a.getBoundingClientRect().left>=0})()`);
// Reduced-motion: check computed preference on representative routes and retained visible content.
await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
const reduced = [];
for (const [name, path] of [['landing','/'],['overview','/app'],['monitoring','/app/monitoring'],['federation','/app/federation'],['live','/app/federation/live'],['models','/app/models'],['ml','/app/research/ml'],['fl','/app/research/fl']]) {
  await goto(path);
  await waitFor(`document.body.innerText.trim().length>100`);
  const value = await evalJs(`(()=>({matches:matchMedia('(prefers-reduced-motion: reduce)').matches,visible:document.body.innerText.trim().length>100}))()`);
  reduced.push({ name, ...value });
}
await cdp.send('Emulation.setEmulatedMedia', { features: [] });
await viewport(390); await goto('/app');
const menuFocused = await evalJs(`(()=>{const menu=document.querySelector('button[aria-label="Open navigation"]');menu?.focus();const focused=document.activeElement===menu;menu?.click();return focused})()`);
await waitFor(`document.querySelector('button.menu')?.getAttribute('aria-expanded')==='true'`);
const keyboard = await evalJs(`(()=>({menuExpanded:document.querySelector('button.menu')?.getAttribute('aria-expanded'),skipLink:!!document.querySelector('a[href="#main-content"]'),positiveTabindex:document.querySelectorAll('[tabindex]:not([tabindex="-1"]):not([tabindex="0"])').length}))()`);
keyboard.menuFocused = menuFocused;
await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape' });
await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape' });
await waitFor(`document.querySelector('button.menu')?.getAttribute('aria-expanded')==='false'`);
keyboard.escapeClosesAndRestoresFocus = await evalJs(`document.activeElement===document.querySelector('button.menu')`);
await goto('/app/history');
await waitFor(`document.body.innerText.includes(${JSON.stringify(sessionId)})`);
keyboard.historyEvidenceFocusable = await evalJs(`(()=>{const a=document.querySelector('.mobile-list .cta');a?.focus();return {passed:document.activeElement===a,found:!!a,active:document.activeElement?.outerHTML?.slice(0,160),link:a?.outerHTML?.slice(0,160)}})()`);
await goto('/app/system');
keyboard.disclosureFocusable = await evalJs(`(()=>{const s=document.querySelector('details summary');s?.focus();return document.activeElement===s})()`);
keyboard.signOutFocusable = await evalJs(`(()=>{const b=document.querySelector('button[aria-label="Sign out"]');b?.focus();return document.activeElement===b})()`);
const externalHosts = [...hosts].filter((host) => host && host !== '127.0.0.1' && host !== 'localhost');
const result = { stage, auth: 'DEMO', sessionId, monitoring, pages: records, reduced, keyboard,
  visualChecks: { formLabelsSeparated, historyEvidenceVisible },
  externalHosts, consoleErrors: errors, networkFailures,
  passed: monitoring.state === 'COMPLETED' && monitoring.model === 'MODEL_V2_FINAL' && monitoring.calibration?.includes('CAL_V2')
    && records.every((r) => Object.values(r.widths).every((w) => !w.overflow && w.h1.length === 1))
    && reduced.every((r) => r.matches && r.visible) && keyboard.menuFocused && keyboard.menuExpanded === 'true'
    && keyboard.skipLink && keyboard.positiveTabindex === 0 && keyboard.escapeClosesAndRestoresFocus
    && keyboard.historyEvidenceFocusable.passed && keyboard.disclosureFocusable && keyboard.signOutFocusable
    && formLabelsSeparated && historyEvidenceVisible && !externalHosts.length && !errors.length };
writeFileSync(`${outDir}/browser_smoke.json`, JSON.stringify(result, null, 2) + '\n');
cdp.ws.close();
if (stage === 'final' && !result.passed) throw new Error('UI_ENH_003_BROWSER_FAIL:' + JSON.stringify({ monitoring, externalHosts, errors, networkFailures }));
console.log(JSON.stringify({ passed: result.passed, stage, sessionId, pages: records.length }));
