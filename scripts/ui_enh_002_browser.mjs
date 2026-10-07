// UI-ENH-002 real-Chrome offline DEMO smoke. No mocked API, inference, or federation.
// node scripts/ui_enh_002_browser.mjs <debugPort> <frontendOrigin> <outJson> <shotsDir>
import { mkdirSync, writeFileSync } from 'node:fs';

const [, , debugPort, origin, outPath, shotsDir] = process.argv;
mkdirSync(shotsDir, { recursive: true });
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
const cdp = new Cdp(targets.find((target) => target.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const hosts = new Set(), errors = [], failed = [];
cdp.on((method, params) => {
  if (method === 'Network.requestWillBeSent') { try { hosts.add(new URL(params.request.url).hostname); } catch {} }
  if (method === 'Network.loadingFailed' && !params.canceled) failed.push(params.errorText);
  if (method === 'Runtime.exceptionThrown') errors.push(String(params.exceptionDetails?.exception?.description ?? params.exceptionDetails?.text));
  if (method === 'Runtime.consoleAPICalled' && params.type === 'error') errors.push(params.args.map((arg) => arg.value ?? arg.description).join(' '));
});
for (const domain of ['Page', 'Runtime', 'Network']) await cdp.send(`${domain}.enable`);
const evalJs = async (expression) => {
  const result = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(`Browser evaluation failed: ${expression.slice(0, 80)}`);
  return result.result.value;
};
const waitFor = async (expression, timeout = 60000) => {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    try { if (await evalJs(expression)) return; } catch {}
    await sleep(100);
  }
  throw new Error(`Timed out: ${expression.slice(0, 90)}`);
};
const goto = async (path) => { await cdp.send('Page.navigate', { url: origin + path }); await sleep(250); };
const viewport = (width) => cdp.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width <= 768 });
const click = (label) => evalJs(`(()=>{const e=[...document.querySelectorAll('button,a')].find(x=>x.textContent.trim()===${JSON.stringify(label)});if(!e||e.disabled)return false;e.click();return true})()`);
const clickId = (id) => evalJs(`(()=>{const e=document.querySelector('[data-testid=${JSON.stringify(id)}]');if(!e||e.disabled)return false;e.click();return true})()`);
const pageFacts = () => evalJs(`(()=>({h1:[...document.querySelectorAll('h1')].map(x=>x.textContent.trim()),main:document.querySelectorAll('main').length,scrollWidth:document.documentElement.scrollWidth,width:innerWidth,body:document.body.innerText.slice(0,16000)}))()`);
const shot = async (name) => { const result = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(`${shotsDir}/${name}.png`, Buffer.from(result.data, 'base64')); };

await viewport(1440); await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
if (!await click('ENTER DEMO WORKSPACE')) throw new Error('Demo entry not clickable');
await waitFor(`location.pathname==='/app' && !!document.querySelector('[data-testid="demo-banner"]')`);
const pages = [
  ['overview', '/app', 'NHM research system'],
  ['models', '/app/models', 'Model governance & comparison'],
  ['monitoring', '/app/monitoring', 'Live monitoring'],
  ['research_ml', '/app/research/ml', 'MODEL_V2_NOT_PROMOTED_RELEASE_CI'],
  ['research_fl', '/app/research/fl', 'V2-FL-005 is not scientific efficacy'],
  ['federation', '/app/federation', 'Federation Studio'],
];
const records = [];
for (const [name, path, expected] of pages) {
  const widths = {};
  for (const width of [1440, 1024, 768, 390]) {
    await viewport(width); await goto(path);
    await waitFor(`document.body.innerText.includes(${JSON.stringify(expected)})`);
    if (name.startsWith('research_')) await waitFor(`!!document.querySelector('[data-testid="full-frozen-evidence"]')`);
    await sleep(350);
    const facts = await pageFacts();
    widths[width] = { overflow: facts.scrollWidth > facts.width + 1, h1: facts.h1, main: facts.main,
      keyText: facts.body.includes(expected), authDemo: facts.body.includes('OFFLINE DEMO IDENTITY') };
    if (width === 1440 || width === 390) await shot(`${name}_${width}`);
  }
  records.push({ name, path, widths });
}

await viewport(1440); await goto('/app/device');
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
const monitoring = await evalJs(`(()=>({state:document.querySelector('[data-testid="session-state"]')?.textContent.trim(),model:document.querySelector('[data-testid="inf-model"]')?.textContent.trim(),calibration:document.querySelector('[data-testid="inf-cal"]')?.textContent.trim(),qualityVisible:!!document.querySelector('[data-testid="quality-state"]'),researchStateVisible:!!document.querySelector('[data-testid="monitoring-state"]'),flow:document.querySelector('[data-testid="monitoring-flow"]')?.textContent}))()`);
await shot('monitoring_completed_1440');
const externalHosts = [...hosts].filter((host) => host !== '127.0.0.1' && host !== 'localhost');
const result = { auth: 'DEMO', pages: records, monitoring: { sessionId, ...monitoring },
  federationNavigation: records.find((record) => record.name === 'federation'), externalHosts,
  consoleErrors: errors, networkFailures: failed,
  passed: records.every((record) => Object.values(record.widths).every((w) => !w.overflow && w.h1.length === 1 && w.main === 1 && w.keyText && w.authDemo))
    && monitoring.state === 'COMPLETED' && monitoring.model === 'MODEL_V2_FINAL'
    && monitoring.calibration?.includes('CAL_V2') && externalHosts.length === 0 && errors.length === 0 };
writeFileSync(outPath, JSON.stringify(result, null, 2) + '\n');
cdp.ws.close();
if (!result.passed) throw new Error('UI_ENH_002_BROWSER_SMOKE_FAIL:' + JSON.stringify({ monitoring, externalHosts, errors, failed }));
console.log(JSON.stringify({ passed: result.passed, sessionId, pages: records.length }));
