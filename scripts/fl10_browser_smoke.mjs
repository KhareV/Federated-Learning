// Real Chrome smoke against an isolated local DEMO stack. No mocked FL10 response.
import { mkdirSync, writeFileSync } from 'node:fs';

const [, , debugPort, origin, output] = process.argv;
mkdirSync(output, { recursive: true });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const page = targets.find((item) => item.type === 'page');
if (!page) throw new Error('NO_CHROME_PAGE');
const ws = new WebSocket(page.webSocketDebuggerUrl);
const pending = new Map();
let nextId = 0;
const errors = [];
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
ws.onmessage = ({ data }) => {
  const message = JSON.parse(data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
  }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails?.text ?? 'exception');
  if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push('console.error');
};
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId; pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params }));
});
for (const domain of ['Page', 'Runtime', 'Network']) await send(`${domain}.enable`);
const evaluate = async (expression) => {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw new Error(`EVALUATE_FAILED:${expression.slice(0, 80)}`);
  return result.result.value;
};
const wait = async (expression, timeout = 45000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await evaluate(expression)) return; await sleep(150); }
  const state = await evaluate(`({path:location.pathname,body:document.body?.innerText?.slice(0,400)})`);
  throw new Error(`WAIT_TIMEOUT:${expression}:${JSON.stringify(state)}:${JSON.stringify(errors)}`);
};
const navigate = async (path) => {
  await send('Page.navigate', { url: origin + path });
  await wait(`location.pathname===${JSON.stringify(path)}`);
};
const screenshot = async (name) => {
  const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  writeFileSync(`${output}/${name}.png`, Buffer.from(data, 'base64'));
};
const viewport = (width) => send('Emulation.setDeviceMetricsOverride', {
  width, height: 900, deviceScaleFactor: 1, mobile: width < 700,
});
await viewport(1440);
await navigate('/sign-in');
await wait(`document.body.innerText.includes('ENTER DEMO WORKSPACE') || location.pathname==='/app'`);
if (await evaluate(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`)) {
  await evaluate(`([...document.querySelectorAll('button,a')].find(x=>x.textContent.trim()==='ENTER DEMO WORKSPACE')).click()`);
}
await wait(`location.pathname==='/app'`);
await navigate('/app/observatory/fl10');
await wait(`document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length>=3`, 60000);
const tabs = ['overview', 'training', 'classification', 'clients', 'comparisons', 'internals', 'bridge', 'exports'];
const tabResults = {};
for (const tab of tabs) {
  await evaluate(`([...document.querySelectorAll('[role="tab"]')].find(x=>x.textContent.trim()===${JSON.stringify({ overview:'Overview', training:'Training', classification:'Classification', clients:'Clients', comparisons:'R3 vs R10', internals:'Optimizer & federation', bridge:'Research bridge', exports:'Exports' }[tab])})).click()`);
  await wait(`!!document.querySelector('[data-testid="tab-${tab}"]')`);
  tabResults[tab] = await evaluate(`(()=>({charts:document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length,tables:document.querySelectorAll('details.datatable, details.fl10-table').length,overflow:document.documentElement.scrollWidth>innerWidth}))()`);
  if (tab === 'classification' || tab === 'internals') await screenshot(`${tab}_1440`);
}
await evaluate(`([...document.querySelectorAll('[role="tab"]')].find(x=>x.textContent.trim()==='Overview')).click()`);
const desktop = await evaluate(`(()=>({source:document.querySelector('[data-testid="source-label"]')?.textContent,updates:document.querySelector('[data-testid="accepted-updates"]')?.textContent,charts:document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length,overflow:document.documentElement.scrollWidth>innerWidth,warning:document.body.innerText.includes('NOT AAMI-SVF')}))()`);
await screenshot('overview_1440');
const intermediate = {};
for (const width of [1024, 768]) {
  await viewport(width); await sleep(300);
  intermediate[width] = await evaluate(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,visibleTabs:document.querySelectorAll('[role="tab"]').length,chart:document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length}))()`);
  await screenshot(`overview_${width}`);
}
await viewport(390); await sleep(400);
const mobile = await evaluate(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,visibleTabs:document.querySelectorAll('[role="tab"]').length,chart:document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length}))()`);
await screenshot('overview_390');
await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
const reducedMotion = await evaluate(`(()=>({matches:matchMedia('(prefers-reduced-motion: reduce)').matches,charts:document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length,controls:document.querySelectorAll('[role="tab"]').length,overflow:document.documentElement.scrollWidth>innerWidth}))()`);
const keyboard = await evaluate(`(()=>{const b=document.querySelector('[role="tab"]');b.focus();return {focusVisible:document.activeElement===b,accessibleName:!!b?.textContent?.trim()}})()`);
const report = { passed: desktop.updates === '80' && desktop.warning && !desktop.overflow && !mobile.overflow && Object.values(intermediate).every((v) => !v.overflow) && tabs.every((tab) => !tabResults[tab].overflow) && reducedMotion.matches && reducedMotion.charts>0 && keyboard.focusVisible && errors.length === 0,
  desktop, intermediate, mobile, reducedMotion, keyboard, tabs: tabResults, errors, source: origin, note: 'DEMO browser smoke; Clerk ownership not claimed' };
writeFileSync(`${output}/fl10_browser_smoke.json`, JSON.stringify(report, null, 2) + '\n');
ws.close();
console.log(JSON.stringify(report));
if (!report.passed) process.exitCode = 1;
