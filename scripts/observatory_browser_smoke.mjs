// Real Chrome against the local Observatory API + SvelteKit; no mocked responses.
import { mkdirSync, writeFileSync } from 'node:fs';

const [, , debugPort, origin, output] = process.argv;
mkdirSync(output, { recursive: true });
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
  send(method, params = {}) {
    const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((yes, no) => this.pending.set(id, { yes, no }));
  }
  on(fn) { this.handlers.push(fn); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
await cdp.ready;
const errors = [], hosts = new Set(), captureRequests = [];
cdp.on((method, params) => {
  if (method === 'Runtime.exceptionThrown') errors.push(params.exceptionDetails?.text ?? 'exception');
  if (method === 'Runtime.consoleAPICalled' && params.type === 'error') errors.push('console.error');
  if (method === 'Network.requestWillBeSent') {
    if (params.request.url.includes('/observatory/sessions/') && params.request.url.includes('/capture')) captureRequests.push(params.request.url);
    try { const u = new URL(params.request.url); if (u.protocol === 'http:' || u.protocol === 'https:') hosts.add(u.hostname); } catch {}
  }
});
for (const domain of ['Page','Runtime','Network']) await cdp.send(`${domain}.enable`);
const evaluate = async (expression) => {
  const response = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) throw new Error(`EVAL_FAILED:${expression.slice(0, 80)}`);
  return response.result.value;
};
const wait = async (expression, timeout = 30000) => {
  const until = Date.now() + timeout;
  while (Date.now() < until) { if (await evaluate(expression)) return; await sleep(100); }
  throw new Error(`TIMEOUT:${expression.slice(0, 100)}`);
};
const navigate = async (path) => { await cdp.send('Page.navigate', { url: origin + path }); await wait(`location.pathname===${JSON.stringify(path)}`); };
const viewport = (width) => cdp.send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 700 });
const deadline = (promise, ms, label) => new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error(`TIMEOUT:${label}`)), ms);
  promise.then((value) => { clearTimeout(timer); resolve(value); }, (error) => { clearTimeout(timer); reject(error); });
});
const screenshot = async (name) => {
  const result = await deadline(cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }), 15000, `screenshot:${name}`);
  writeFileSync(`${output}/${name}.png`, Buffer.from(result.data, 'base64'));
};
await viewport(1440);
await navigate('/sign-in');
await wait(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
await evaluate(`[...document.querySelectorAll('button,a')].find(x=>x.textContent.trim()==='ENTER DEMO WORKSPACE').click()`);
await wait(`location.pathname==='/app'`);
await navigate('/app/observatory');
await wait(`!!document.querySelector('[data-testid="signal-PREPROC_V1_ECG_FILTER_V1"]')`, 60000);
const clean = await evaluate(`(()=>({h1:document.querySelector('main h1')?.textContent,stages:document.querySelectorAll('figure.signal').length,cursors:document.querySelectorAll('figure.signal input[type=range]').length,pinnedCodeRefs:document.querySelectorAll('details.evidence li code').length,commit:document.querySelector('details.evidence p code')?.textContent,quality:document.body.innerText.includes('VALID'),overflow:document.documentElement.scrollWidth>innerWidth}))()`);
await screenshot('clean_1440');
const sessionAvailable = await evaluate(`document.querySelectorAll('select')[1]?.options.length>1`);
let ownedSession = null;
if (sessionAvailable) {
  await evaluate(`(()=>{const s=document.querySelectorAll('select')[1];s.selectedIndex=1;s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
  await wait(`document.body.innerText.includes('PERSISTED MODEL RESULT')`, 60000);
  ownedSession = await evaluate(`(()=>({model:document.body.innerText.includes('MODEL_V2_FINAL'),calibration:document.body.innerText.includes('CAL_V2'),technical:document.body.innerText.includes('RESEARCH TECHNICAL METADATA'),withheld:document.body.innerText.includes('WITHHELD_SENTINEL')}))()`);
  await screenshot('owned_session_inference_1440');
}
const captureSession = process.env.NHM_OBSERVATORY_CAPTURE_SESSION_ID;
let capturedSession = null;
if (captureSession) {
  await evaluate(`(()=>{const s=document.querySelectorAll('select')[1];s.value=${JSON.stringify(captureSession)};s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
  await wait(`(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('Open captured live window if available'));return b && !b.disabled})()`);
  await evaluate(`([...document.querySelectorAll('button')].find(x=>x.textContent.includes('Open captured live window if available'))).click()`);
  try {
    await wait(`document.body.innerText.includes('CAPTURED FROM THIS LIVE PREPROCESSING RUNTIME') && document.body.innerText.includes('PERSISTED MODEL RESULT')`, 20000);
  } catch (cause) {
    const state = await evaluate(`(()=>({selected:document.querySelectorAll('select')[1]?.value,error:document.querySelector('[role=alert]')?.innerText,classification:document.querySelector('.classification')?.innerText,loading:document.querySelector('[role=status]')?.innerText}))()`);
    throw new Error(`LIVE_CAPTURE_BROWSER_NOT_READY:${JSON.stringify(state)}:${JSON.stringify(captureRequests)}:${cause}`);
  }
  capturedSession = await evaluate(`(()=>({classification:document.body.innerText.includes('CAPTURED FROM THIS LIVE PREPROCESSING RUNTIME'),model:document.body.innerText.includes('MODEL_V2_FINAL'),stages:document.querySelectorAll('figure.signal').length,overflow:document.documentElement.scrollWidth>innerWidth}))()`);
  await screenshot('captured_live_session_1440');
  await viewport(390); await sleep(350);
  capturedSession.mobileOverflow = await evaluate(`document.documentElement.scrollWidth>innerWidth`);
  await screenshot('captured_live_session_390');
  await viewport(1440);
}
await evaluate(`(()=>{const s=document.querySelector('select');s.value='DISCONNECT_RECONNECT';s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
await wait(`document.body.innerText.includes('DISCONNECT_RECONNECT') && !!document.querySelector('[data-testid="signal-PREPROC_V1_ECG_FILTER_V1"]')`);
await evaluate(`(()=>{const r=document.querySelector('input[type=range]');r.value='12';r.dispatchEvent(new Event('input',{bubbles:true}))})()`);
await wait(`document.body.innerText.includes('UNUSABLE') && document.body.innerText.includes('LONG')`, 60000);
const gap = await evaluate(`(()=>({quality:document.body.innerText.includes('UNUSABLE'),longGap:document.body.innerText.includes('LONG'),notApplied:document.body.innerText.includes('NOT APPLIED'),overflow:document.documentElement.scrollWidth>innerWidth}))()`);
await screenshot('long_gap_1440');
await viewport(390); await sleep(350);
const mobile = await evaluate(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,h1:document.querySelectorAll('main h1').length,charts:document.querySelectorAll('figure.signal').length}))()`);
await screenshot('long_gap_390');
await viewport(1440);
await navigate('/app/observatory/federation');
await wait(`document.body.innerText.includes('SIM_FL_SITE_07') && document.body.innerText.includes('723') && (document.body.innerText.includes('Accepted by coordinator') || document.body.innerText.includes('No owned run selected'))`);
const federation = await evaluate(`(()=>({clients:document.querySelectorAll('.roster button').length,cohort:document.body.innerText.includes('WEARABLE_SIM_EVENT_WINDOW_V1'),runEvidence:document.body.innerText.includes('Accepted by coordinator')||document.body.innerText.includes('No owned run selected'),overflow:document.documentElement.scrollWidth>innerWidth}))()`);
await screenshot('federation_cohort_1440');
const matrix = await evaluate(`(()=>{const panel=document.querySelector('details.matrix');if(!panel)return {available:false};panel.open=true;return {available:true,rows:panel.querySelectorAll('tbody tr').length,rounds:panel.querySelectorAll('thead th').length-1,attested:panel.innerText.includes('Accepted · governance-attested'),unknown:panel.innerText.includes('Trained · acceptance unavailable')}})()`);
if (matrix.available) await screenshot('federation_round_matrix_1440');
await viewport(390); await sleep(350);
const federationMobile = await evaluate(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,clients:document.querySelectorAll('.roster button').length}))()`);
await screenshot('federation_cohort_390');
await viewport(1440);
await navigate('/app/observatory/federation/SIM_FL_SITE_07');
await wait(`document.body.innerText.includes('SIM_FL_SITE_07: inspect one local window') && !!document.querySelector('[data-testid="signal-PREPROC_V1_ECG_FILTER_V1"]')`, 60000);
await evaluate(`(()=>{const r=document.querySelector('input[type=range]');r.value='48';r.dispatchEvent(new Event('input',{bubbles:true}))})()`);
try {
  await wait(`document.body.innerText.includes('LONG_GAP_SPAN') && document.body.innerText.includes('EXCLUDED')`, 60000);
} catch (cause) {
  const state = await evaluate(`(()=>({range:document.querySelector('input[type=range]')?.value,output:document.querySelector('.stepper output')?.innerText,error:document.querySelector('[role=alert]')?.innerText,loading:document.querySelector('[role=status]')?.innerText,summary:document.querySelector('.summary')?.innerText}))()`);
  throw new Error(`FL_WINDOW_BROWSER_NOT_READY:${JSON.stringify(state)}:${cause}`);
}
const flWindow = await evaluate(`(()=>({excluded:document.body.innerText.includes('EXCLUDED'),unusable:document.body.innerText.includes('UNUSABLE'),labelWithheld:document.body.innerText.includes('NOT ASSIGNED'),noTraining:document.body.innerText.includes('No FL training or model inference occurs'),overflow:document.documentElement.scrollWidth>innerWidth}))()`);
await screenshot('fl_site07_long_gap_1440');
await viewport(390); await sleep(350);
const flWindowMobile = await evaluate(`document.documentElement.scrollWidth>innerWidth`);
await screenshot('fl_site07_long_gap_390');
await viewport(1440);
await navigate('/app/observatory/research');
await wait(`document.body.innerText.includes('Inspect an authorized research window') && !!document.querySelector('[data-testid="signal-PREPROC_V1_FILTERED_TRAIN_CACHE"]')`, 60000);
const researchRecord = await evaluate(`(()=>({train:document.body.innerText.includes('MIT-BIH · TRAIN'),actualSignal:!!document.querySelector('[data-testid="signal-PREPROC_V1_FILTERED_TRAIN_CACHE"]'),annotationUnavailable:document.body.innerText.includes('RAW WFDB FILES NOT PRESENT'),splitBoundary:document.body.innerText.includes('INTERNAL_TEST'),overflow:document.documentElement.scrollWidth>innerWidth}))()`);
await screenshot('research_train_window_1440');
await viewport(390); await sleep(350);
const researchRecordMobile = await evaluate(`document.documentElement.scrollWidth>innerWidth`);
await screenshot('research_train_window_390');
await viewport(1440);
await navigate('/app/observatory/tour');
await wait(`document.body.innerText.includes('Follow the evidence, end to end') && document.body.innerText.includes('LOADED')`);
const tour = await evaluate(`(()=>({steps:document.querySelectorAll('nav[aria-label="Tour steps"] li').length,loaded:document.body.innerText.includes('ML LOADED')&&document.body.innerText.includes('FL LOADED'),overflow:document.documentElement.scrollWidth>innerWidth}))()`);
await screenshot('guided_tour_1440');
await viewport(390); await sleep(350);
const tourMobile = await evaluate(`document.documentElement.scrollWidth>innerWidth`);
await screenshot('guided_tour_390');
const responsive = [];
for (const width of [1024, 768]) {
  await viewport(width);
  for (const route of ['/app/observatory', '/app/observatory/federation', '/app/observatory/federation/SIM_FL_SITE_07', '/app/observatory/research', '/app/observatory/tour']) {
    await navigate(route);
    await wait(`!!document.querySelector('main h1')`);
    await sleep(250);
    responsive.push({ width, route, overflow: await evaluate(`document.documentElement.scrollWidth>innerWidth`) });
  }
}
await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
await viewport(390);
await navigate('/app/observatory/tour');
await wait(`document.body.innerText.includes('Follow the evidence, end to end')`);
const reducedMotion = await evaluate(`matchMedia('(prefers-reduced-motion: reduce)').matches && !(document.documentElement.scrollWidth>innerWidth)`);
const externalHosts = [...hosts].filter((x) => x !== '127.0.0.1' && x !== 'localhost');
const report = { clean, ownedSession, capturedSession, gap, mobile, federation, matrix, federationMobile, flWindow, flWindowMobile, researchRecord, researchRecordMobile, tour, tourMobile, responsive, reducedMotion, externalHosts, errors,
  passed: clean.h1 === 'Follow one signal through the system' && clean.stages === 5 && clean.cursors === 5 && clean.pinnedCodeRefs === 5 && clean.commit === 'dff28f6a7b7bd527def21cb9fd95d682aa60a667' && clean.quality && !clean.overflow
    && (!sessionAvailable || (ownedSession.model && ownedSession.calibration && ownedSession.technical && !ownedSession.withheld))
    && (!captureSession || (capturedSession?.classification && capturedSession?.model && capturedSession?.stages === 5 && !capturedSession?.overflow && !capturedSession?.mobileOverflow))
    && gap.quality && gap.longGap && gap.notApplied && !gap.overflow
    && !mobile.overflow && mobile.h1 === 1 && mobile.charts === 4
    && federation.clients === 8 && federation.cohort && federation.runEvidence && !federation.overflow
    && (!matrix.available || (matrix.rows === 8 && matrix.rounds === 3 && (matrix.attested || matrix.unknown)))
    && federationMobile.clients === 8 && !federationMobile.overflow
    && flWindow.excluded && flWindow.unusable && flWindow.labelWithheld && flWindow.noTraining
    && !flWindow.overflow && !flWindowMobile
    && researchRecord.train && researchRecord.actualSignal && researchRecord.annotationUnavailable && researchRecord.splitBoundary && !researchRecord.overflow && !researchRecordMobile
    && tour.steps === 16 && tour.loaded && !tour.overflow && !tourMobile
    && responsive.every((item) => !item.overflow) && reducedMotion
    && !externalHosts.length && !errors.length };
writeFileSync(`${output}/browser_smoke.json`, JSON.stringify(report, null, 2) + '\n');
cdp.ws.close();
if (!report.passed) throw new Error(`OBSERVATORY_BROWSER_FAILED:${JSON.stringify(report)}`);
console.log(JSON.stringify(report));
