// Minimal Chrome DevTools Protocol helper for the unified Federation Studio browser checks (no mocked responses).
import { mkdirSync, writeFileSync } from 'node:fs';

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function connect(debugPort, origin, output) {
  mkdirSync(output, { recursive: true });
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
  const page = targets.find((item) => item.type === 'page');
  if (!page) throw new Error('NO_CHROME_PAGE');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  const pending = new Map();
  const errors = [];
  let nextId = 0;
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
    }
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails?.text ?? 'exception');
    if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push('console.error:' + (message.params.args?.[0]?.value ?? ''));
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId; pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  for (const domain of ['Page', 'Runtime', 'Network']) await send(`${domain}.enable`);
  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(`EVALUATE_FAILED:${expression.slice(0, 120)}:${JSON.stringify(result.exceptionDetails).slice(0, 300)}`);
    return result.result.value;
  };
  const wait = async (expression, timeout = 60000) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) { if (await evaluate(expression)) return; await sleep(200); }
    const state = await evaluate(`({path:location.pathname+location.search,body:document.body?.innerText?.slice(0,400)})`);
    throw new Error(`WAIT_TIMEOUT:${expression}:${JSON.stringify(state)}:${JSON.stringify(errors.slice(-5))}`);
  };
  const navigate = async (path, ready = 'true') => {
    await send('Page.navigate', { url: origin + path });
    await sleep(300);
    await wait(`document.readyState==='complete' && (${ready})`);
  };
  const screenshot = async (name, full = true) => {
    const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: full });
    writeFileSync(`${output}/${name}.png`, Buffer.from(data, 'base64'));
  };
  // mobile=false on purpose: mobile emulation silently widens the layout viewport to fit overflowing content, which would hide real horizontal overflow.
  const viewport = (width, height = 900) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  const demoSignIn = async () => {
    await navigate('/sign-in');
    await wait(`document.body.innerText.includes('ENTER DEMO WORKSPACE') || location.pathname==='/app'`);
    if (await evaluate(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`)) {
      await evaluate(`([...document.querySelectorAll('button,a')].find(x=>x.textContent.trim()==='ENTER DEMO WORKSPACE')).click()`);
    }
    await wait(`location.pathname==='/app'`);
  };
  return { send, evaluate, wait, navigate, screenshot, viewport, demoSignIn, errors, close: () => ws.close() };
}
