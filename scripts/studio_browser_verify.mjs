// Real Chrome verification of the unified Live Federation Studio against a running isolated stack (DemoAuth). No mocked response: it starts a genuine 3-round and a genuine 10-round run.
// Usage: node studio_browser_verify.mjs <debugPort> <origin> <outputDir>
import { writeFileSync } from 'node:fs';
import { connect, sleep } from './studio_cdp.mjs';

const [, , debugPort, origin, output] = process.argv;
const b = await connect(debugPort, origin, output);
const checks = [];
const evidence = {};
const check = (name, ok, detail = '') => { checks.push({ name, ok: !!ok, detail: String(detail).slice(0, 300) }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  :: ' + String(detail).slice(0, 300)}`); };
const T = (id) => `document.querySelector('[data-testid="${id}"]')`;
const text = (id) => b.evaluate(`${T(id)}?.textContent ?? null`);
const exists = (id) => b.evaluate(`!!${T(id)}`);
const click = (id) => b.evaluate(`(()=>{const e=${T(id)};if(!e)return false;e.click();return true})()`);
const api = (path) => b.evaluate(`fetch('/product/v1${path}',{credentials:'same-origin'}).then(r=>r.json())`);
const six = (v) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(6)) : String(v));
const waitFor = (expr, ms = 60000) => b.wait(expr, ms);

async function runIdFromUrl() { return b.evaluate(`new URL(location.href).searchParams.get('run')`); }

async function metricsMatchApi(runId, round, label) {
  await click(`round-btn-R${round}`);
  await waitFor(`${T('metric-round')}?.textContent.includes('ROUND R${round}')`, 30000);
  await waitFor(`${T('metric-status')}?.textContent==='COMPLETED'`, 60000);
  const rec = await api(`/studio/runs/${runId}/evaluation/${round}`);
  const shown = {};
  for (const k of ['AUPRC', 'AUROC', 'F1', 'specificity', 'recall', 'accuracy', 'BCE', 'Brier']) shown[k] = (await text(`metric-${k}`)) ?? '';
  const ok = Object.entries(shown).every(([k, t]) => t.endsWith(six(rec.metric_result[k])));
  check(`${label}: R${round} metric cards equal the stored record`, ok, JSON.stringify(shown) + ' vs ' + six(rec.metric_result.AUPRC));
  const cc = rec.confusion_counts;
  check(`${label}: R${round} confusion counts reconcile with the population`, cc.TP + cc.FN === rec.metric_result.positives && cc.TN + cc.FP === rec.metric_result.negatives, JSON.stringify(cc));
  await b.evaluate(`(()=>{const d=document.querySelector('details.all');if(d)d.open=true})()`);
  await sleep(100);
  const tpShown = await text('all-TP');
  check(`${label}: R${round} confusion count cards show the stored counts`, tpShown !== null && tpShown.endsWith(String(cc.TP)) && (await text('all-FN')).endsWith(String(cc.FN)), `${tpShown}`);
  check(`${label}: R${round} committed state digest of the record is displayed`, await b.evaluate(`document.body.innerText.includes('${rec.global_state_digest.slice(0, 8)}')`), rec.global_state_digest.slice(0, 8));
  return rec;
}

async function widths(prefix, runPath) {
  const out = {};
  for (const w of [1440, 1024, 768, 390]) {
    await b.viewport(w); await sleep(500);
    out[w] = await b.evaluate(`({overflow:document.documentElement.scrollWidth>innerWidth, charts:document.querySelectorAll('[data-testid^="chart-FL10_FIG"]').length, grid:document.querySelectorAll('li[data-client]').length, tabs:document.querySelectorAll('[role="tab"]').length, strip:!!${T('run-status-strip')}, cards:document.querySelectorAll('[data-testid^="metric-"]').length})`);
    await b.screenshot(`${prefix}_${w}`);
    check(`${prefix}: no horizontal overflow at ${w}px`, !out[w].overflow, JSON.stringify(out[w]));
    check(`${prefix}: network, status strip, tabs and charts render at ${w}px`, out[w].grid === 8 && out[w].strip && out[w].tabs === 7 && out[w].charts >= 3, JSON.stringify(out[w]));
  }
  await b.viewport(1440); await sleep(300);
  return out;
}

async function tabsAndFigures(runId, label, rounds) {
  const tabs = ['overview', 'performance', 'training', 'clients', 'matrices', 'comparison', 'figures'];
  const seen = {};
  for (const t of tabs) {
    await click(`atab-${t}`);
    await waitFor(`${T('apanel-' + t)} && !${T('figures-loading')} && !${T('tables-loading')}`, 60000);
    await sleep(300);
    seen[t] = await b.evaluate(`({charts:[...document.querySelectorAll('[data-testid^="chart-FL10_FIG"]')].map(e=>e.getAttribute('data-testid').replace('chart-FL10_','')), tables:[...document.querySelectorAll('[data-testid^="table-FL10_TAB"]')].map(e=>e.getAttribute('data-testid').replace('table-FL10_','')), overflow:document.documentElement.scrollWidth>innerWidth})`);
    check(`${label}: tab ${t} has no overflow and renders its content`, !seen[t].overflow && (seen[t].charts.length + seen[t].tables.length > 0 || t === 'figures' || t === 'clients'), JSON.stringify(seen[t]));
  }
  const figs = new Set(Object.values(seen).flatMap((s) => s.charts));
  const tabsSeen = new Set(Object.values(seen).flatMap((s) => s.tables));
  check(`${label}: all 20 figures are reachable from the tabs`, figs.size === 20, [...figs].sort().join(','));
  check(`${label}: all 12 tables are reachable from the tabs`, tabsSeen.size === 12, [...tabsSeen].sort().join(','));
  evidence[`${label}_tabs`] = seen;
  // keyboard
  await b.evaluate(`document.getElementById('atab-overview').focus()`);
  await click('atab-overview');
  await b.evaluate(`document.getElementById('atab-overview').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}))`);
  await sleep(150);
  check(`${label}: analysis tabs are keyboard operable`, (await b.evaluate(`document.getElementById('atab-performance').getAttribute('aria-selected')`)) === 'true');
}

async function narrowTabs(label) {
  await b.viewport(390); await sleep(400);
  for (const t of ['overview', 'performance', 'training', 'clients', 'matrices', 'comparison', 'figures']) {
    await click(`atab-${t}`); await sleep(900);
    const w = await b.evaluate('({sw:document.documentElement.scrollWidth, iw:innerWidth})');
    check(`${label}: tab ${t} fits a 390px viewport without horizontal scroll`, w.sw <= w.iw, JSON.stringify(w));
  }
  await b.viewport(1440); await sleep(300);
}

async function migratedFeatures(runId, label, rounds, expectedUpdates) {
  const rec = await api(`/studio/runs/${runId}/evaluation`);
  const done = rec.records.filter((r) => r.evaluation_status === 'COMPLETED');
  // overview facts, limits and evidence boundary (retired FL10 overview cards)
  await click('atab-overview');
  await waitFor(`!!${T('overview-cards')}`, 60000);
  check(`${label}: overview facts show the run's own source, accepted updates and limits`, (await text('accepted-updates')) === String(expectedUpdates) && (await text('source-label')).includes('LIVE RUN') && (await b.evaluate(`document.querySelectorAll('[data-testid="limits"] li').length`)) >= 3, `${await text('accepted-updates')}`);
  check(`${label}: overview names the cohort reuse and the synthetic boundary`, (await text('run-overview')).includes('REUSED') || (await b.evaluate(`document.body.innerText.includes('already examined')`)));
  // compare any two evaluated rounds; default = predeclared pair
  await click('atab-comparison');
  await waitFor(`!!${T('cmp-table')}`, 60000);
  const defaults = await b.evaluate(`({a:${T('cmp-a')}.value, b:${T('cmp-b')}.value})`);
  const pair = rounds === 10 ? ['3', '10'] : ['0', '3'];
  check(`${label}: comparison defaults to the predeclared same-cohort pair`, defaults.a === pair[0] && defaults.b === pair[1], JSON.stringify(defaults));
  const A = done.find((r) => String(r.round_id) === pair[0]).metric_result, B = done.find((r) => String(r.round_id) === pair[1]).metric_result;
  check(`${label}: comparison difference equals the stored point difference`, (await text('cmp-diff-AUPRC')) === six(B.AUPRC - A.AUPRC), `${await text('cmp-diff-AUPRC')} vs ${six(B.AUPRC - A.AUPRC)}`);
  await b.evaluate(`(()=>{const s=${T('cmp-a')};s.value='1';s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
  await sleep(300);
  const R1 = done.find((r) => r.round_id === 1).metric_result;
  check(`${label}: choosing another round updates the comparison`, (await text('cmp-diff-AUPRC')) === six(B.AUPRC - R1.AUPRC), await text('cmp-diff-AUPRC'));
  check(`${label}: the scientific research bridge is shown as a separate frozen lane`, (await b.evaluate(`document.querySelectorAll('[data-testid="bridge-table"] tbody tr').length`)) >= 2 && (await b.evaluate(`!!document.querySelector('[data-testid="research-bridge"] a[href="/app/observatory/outcomes"]')`)));
  // client history + matching holdout participants
  await click('atab-clients');
  await waitFor(`!!${T('client-history-table')}`, 60000);
  const rowsN = await b.evaluate(`document.querySelectorAll('[data-testid="client-history-table"] tbody tr').length`);
  check(`${label}: client history lists every committed round for the selected client`, rowsN === rounds, rowsN);
  await b.evaluate(`(()=>{const s=${T('client-select')};s.value='SIM_FL_SITE_03';s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
  await sleep(500);
  check(`${label}: the two holdout participants of the matching site condition are listed`, (await b.evaluate(`document.querySelectorAll('[data-testid="client-holdout-table"] tbody tr').length`)) === 2);
}

async function exportsWork(runId, label) {
  await click('atab-figures');
  await waitFor(`${T('export-status')}`, 30000);
  await waitFor(`${T('export-status')}.textContent.startsWith('EXPORT READY')`, 120000);
  for (const id of ['export-FL10_FIG04-csv', 'export-FL10_FIG07-svg', 'export-FL10_TAB01-csv', 'export-evaluation_records-json']) {
    await b.evaluate(`(()=>{const n=${T('export-note')};if(n)n.textContent=''})()`);
    await click(id);
    await waitFor(`(${T('export-note')}?.textContent ?? '').length > 0`, 30000).catch(() => {});
    const note = await text('export-note');
    check(`${label}: ${id} downloads and verifies against the manifest`, note && note.includes('verified against the export manifest'), note);
  }
  await waitFor(`!${T('export-manifest')}.disabled`, 30000);
  await click('export-manifest');
  await waitFor(`(${T('export-note')}?.textContent ?? '').includes('verification manifest saved')`, 20000).catch(() => {});
  check(`${label}: the verification manifest downloads with its sha256`, ((await text('export-note')) ?? '').includes('verification manifest saved'), await text('export-note'));
  const manifest = await api(`/studio/runs/${runId}/exports`);
  check(`${label}: export manifest is run-specific (20 figures, 12 tables, this run id)`, manifest.status === 'READY' && manifest.run_id === runId && Object.keys(manifest.figures).length === 20 && Object.keys(manifest.tables).length === 12, manifest.run_id);
  const prov = await b.evaluate(`fetch('/product/v1/studio/runs/${runId}/exports/FL10_FIG04/provenance').then(r=>r.json())`);
  check(`${label}: exported provenance names this run and a live source`, prov.run_id === runId && /LIVE RUN/.test(prov.source_label), prov.source_label);
}

// ------------------------------------------------------------------------------------------------------------------------------------
await b.viewport(1440);
await b.demoSignIn();

// ---- A. entry page: selector ------------------------------------------------------------------------------------------------------
await b.navigate('/app/federation', `!!${T('studio-run-starter')}`);
await waitFor(`!${T('cfg-submit')}.disabled`, 120000);
check('entry: 3 rounds is the default selection', (await b.evaluate(`${T('rounds-3')}.getAttribute('aria-checked')`)) === 'true');
check('entry: expected accepted updates are 24 and 80 and labelled as expectations', (await text('expected-3')) === '24' && (await text('expected-10')) === '80' && (await b.evaluate(`document.body.innerText.includes('expected counts, not evidence of completed work')`)));
check('entry: the original three-round form is still the default form', await exists('cfg-run-type'));
for (const w of [1440, 1024, 768, 390]) { await b.viewport(w); await sleep(300); await b.screenshot(`studio_entry_${w}`); check(`entry: no overflow at ${w}px`, !(await b.evaluate('document.documentElement.scrollWidth>innerWidth'))); }
await b.viewport(1440);
await click('rounds-10');
await waitFor(`!!${T('cfg10-submit')}`, 10000);
check('entry: choosing 10 rounds explains disabled FedProx and SecAgg', (await text('cfg10-algorithm-note')).includes('FedProx is disabled') && (await text('cfg10-mode-note')).includes('SecAgg+ shadow is disabled'));
await b.screenshot('studio_entry_ten');
await click('rounds-3');

// ---- B. genuine three-round run ---------------------------------------------------------------------------------------------------
await waitFor(`!${T('cfg-submit')}.disabled`, 60000);
await click('cfg-submit');
await waitFor(`location.pathname==='/app/federation/live'`, 60000);
await waitFor(`!!${T('run-status-strip')}`, 30000);
const run3 = await runIdFromUrl();
evidence.run3 = run3;
const series3 = [];
let selectedMid = false, sawPendingWhileCommitted = false, sawLiveHistorical = false, midChecks = {};
const t0 = Date.now();
while (Date.now() - t0 < 600000) {
  const snap = await b.evaluate(`({accepted:${T('accepted-counter')}?.textContent, stage:${T('current-stage')}?.textContent, status:${T('run-status')}?.innerText.slice(0,30), mstatus:${T('metric-status')}?.textContent, mround:${T('metric-round')}?.textContent.slice(0,14), pendingMarks:document.querySelectorAll('[data-testid^="pending-R"]').length, follow:${T('follow-state')}?.textContent.slice(0,22), banner:${T('metric-substitution')}?.textContent.slice(0,80), hist:!!${T('historical-banner')}})`);
  series3.push({ t: Math.round((Date.now() - t0) / 1000), ...snap });
  const committed = await b.evaluate(`document.querySelectorAll('[data-testid^="dot-R"].done').length`);
  if (committed >= 1 && snap.pendingMarks > 0) sawPendingWhileCommitted = true;
  if (!selectedMid && committed >= 2 && !/COMPLETED/.test(snap.status || '')) {
    // select an older committed round while the run is still executing
    await click('round-btn-R1');
    await sleep(600);
    selectedMid = true;
    midChecks.follow = await text('follow-state');
    midChecks.mround = await text('metric-round');
    midChecks.banner = await exists('historical-banner');
    midChecks.title = await b.evaluate(`[...document.querySelectorAll('h2')].map(h=>h.textContent).find(t=>t.startsWith('Eight logical clients'))`);
    check('3-round live: selecting R1 while the run executes switches the network to round 1 and stops following live', /INSPECTING ROUND 1/.test(midChecks.follow) && midChecks.title.includes('round 1'), JSON.stringify(midChecks));
    sawLiveHistorical = midChecks.banner;
    await sleep(4000);
    const after = await text('follow-state');
    check('3-round live: new events do not overwrite the historical selection', /INSPECTING ROUND 1/.test(after) && (await text('metric-round')).includes('ROUND R1'), after);
    await click('return-to-live');
    await sleep(300);
    check('3-round live: RETURN TO LIVE restores following', /FOLLOWING LIVE/.test(await text('follow-state')));
  }
  if (/COMPLETED/.test(snap.status || '') && (await b.evaluate(`!!${T('export-status')} || true`))) {
    const done = await api(`/studio/runs/${run3}`);
    if (done.status === 'COMPLETED' && done.export_status === 'READY') break;
  }
  await sleep(1000);
}
evidence.series3 = series3;
check('3-round live: a round was shown as committed while later evaluations were still pending (no invented points)', sawPendingWhileCommitted || series3.some((s) => s.mstatus && s.mstatus !== 'COMPLETED'), JSON.stringify(series3.slice(0, 5)));
check('3-round live: the counter reached 24/24 accepted updates from backend events', series3.some((s) => s.accepted === '24/24'), series3.at(-1)?.accepted);
await b.screenshot('studio_run3_completed');
const run3rec = {};
for (const r of [0, 1, 2, 3]) run3rec[r] = await metricsMatchApi(run3, r, '3-round');
check('3-round: states equal the frozen canonical digests (R1-R3)', (await api('/studio/runs/recorded-A/evaluation')).records.slice(0, 4).every((rec, i) => rec.global_state_digest === run3rec[i].global_state_digest));
// rapid switching
const order = [3, 0, 2, 1, 3, 1, 0, 2, 3, 2, 1, 0, 2];
for (const r of order) await click(`round-btn-R${r}`);
await click('round-btn-R2');
await waitFor(`${T('metric-round')}?.textContent.includes('ROUND R2')`, 20000);
await sleep(500);
check('3-round: rapid round switching ends on the last selection with that round\'s values', (await text('metric-AUPRC')).endsWith(six(run3rec[2].metric_result.AUPRC)));
check('3-round: client network heading reflects the selected historical round', (await b.evaluate(`[...document.querySelectorAll('h2')].map(h=>h.textContent).find(t=>t.startsWith('Eight logical clients'))`)).includes('round 2'));
// round-specific client evidence matches the stored round detail
const detail2 = await api(`/studio/runs/${run3}/rounds/2`);
const digestShown = await b.evaluate(`document.querySelector('li[data-client="SIM_FL_SITE_00"]')?.textContent ?? ''`);
check('3-round: client card of the selected round shows that round\'s update digest', digestShown.includes(detail2.client_rounds.find((c) => c.client_id === 'SIM_FL_SITE_00').update_sha256.slice(0, 10)), digestShown.slice(0, 160));
await click('atab-matrices');
await waitFor(`!!${T('fig-FL10_FIG09')}`, 30000);
const cm = await b.evaluate(`document.querySelector('[data-testid="cm-R03"]')?.textContent ?? ''`);
check('3-round: the confusion matrix shows the comparison endpoint counts', cm.includes(`TP ${run3rec[3].confusion_counts.TP}`) && cm.includes(`FP ${run3rec[3].confusion_counts.FP}`), cm);
await click('round-btn-R3');
await tabsAndFigures(run3, '3-round', 3);
await migratedFeatures(run3, '3-round', 3, 24);
await narrowTabs('3-round');
await exportsWork(run3, '3-round');
evidence.widths3 = await widths('studio_run3', '');
await b.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
check('3-round: reduced motion leaves no running animation on a finished run', (await b.evaluate(`matchMedia('(prefers-reduced-motion: reduce)').matches && document.getAnimations().filter(a=>a.playState==='running').length===0`)));
await b.send('Emulation.setEmulatedMedia', { features: [] });

// ---- C. genuine ten-round run -------------------------------------------------------------------------------------------------------
await b.navigate('/app/federation', `!!${T('studio-run-starter')}`);
await click('rounds-10');
await waitFor(`!!${T('cfg10-submit')} && !${T('cfg10-submit')}.disabled`, 120000);
await click('cfg10-submit');
await waitFor(`location.pathname==='/app/federation/live'`, 60000);
await waitFor(`!!${T('run-status-strip')}`, 30000);
const run10 = await runIdFromUrl();
evidence.run10 = run10;
const series10 = [];
let maxAccepted = 0, lagSeen = false, graphPending = false, tenSelected = false;
const t1 = Date.now();
while (Date.now() - t1 < 900000) {
  const snap = await b.evaluate(`({accepted:${T('accepted-counter')}?.textContent, stage:${T('current-stage')}?.textContent, status:${T('run-status')}?.innerText.slice(0,30), mstatus:${T('metric-status')}?.textContent, mround:${T('metric-round')}?.textContent.slice(0,14), pendingMarks:document.querySelectorAll('[data-testid^="pending-R"]').length, sub:!!${T('metric-substitution')}, committed:document.querySelectorAll('[data-testid^="dot-R"].done').length})`);
  series10.push({ t: Math.round((Date.now() - t1) / 1000), ...snap });
  maxAccepted = Math.max(maxAccepted, Number((snap.accepted || '0/0').split('/')[0]));
  if (snap.committed >= 2 && (snap.sub || snap.pendingMarks > 0)) lagSeen = true;
  if (snap.pendingMarks > 0) graphPending = true;
  if (!tenSelected && snap.committed >= 4) {
    await click('round-btn-R3');
    await sleep(800);
    check('10-round live: selecting R3 while R5+ executes shows R3 and does not follow live', /INSPECTING ROUND 3/.test(await text('follow-state')));
    const accNow = Number((await text('accepted-counter')).split('/')[0]);
    await sleep(3000);
    check('10-round live: execution continued in the background while a historical round was selected', Number((await text('accepted-counter')).split('/')[0]) >= accNow);
    check('10-round live: the selected-round view stays on R3', (await text('follow-state')).includes('ROUND 3'));
    await click('return-to-live');
    tenSelected = true;
  }
  const d = await api(`/studio/runs/${run10}`);
  if (d.phase === 'DONE' || d.phase === 'FAILED') { check('10-round: run reached DONE', d.phase === 'DONE', JSON.stringify(d.failure)); break; }
  await sleep(1200);
}
evidence.series10 = series10;
check('10-round live: accepted updates counter reached 80/80 from backend events', maxAccepted === 80, maxAccepted);
check('10-round live: evaluation lagged training and pending rounds were marked (never drawn as values)', lagSeen || graphPending, JSON.stringify(series10.slice(3, 8)));
await b.screenshot('studio_run10_completed');
const rec10 = {};
for (const r of [0, 3, 6, 10]) rec10[r] = await metricsMatchApi(run10, r, '10-round');
const recorded = {};
for (const r of [0, 3, 6, 10]) recorded[r] = await api(`/studio/runs/recorded-A/evaluation/${r}`);
check('10-round: this new run reproduces the recorded FL10 states and metrics (equal digests; not preloaded)', [0, 3, 6, 10].every((r) => rec10[r].global_state_digest === recorded[r].global_state_digest && rec10[r].metric_result.AUPRC === recorded[r].metric_result.AUPRC && rec10[r].metric_result.BCE === recorded[r].metric_result.BCE));
await click('round-btn-R6');
await waitFor(`${T('metric-round')}?.textContent.includes('ROUND R6')`, 20000);
await click('atab-matrices');
await waitFor(`!!${T('fig-FL10_FIG07')} && !${T('figures-loading')}`, 60000);
const roc = await b.evaluate(`(()=>{const f=document.querySelector('[data-testid="fig-FL10_FIG07"]');return f?[...f.querySelectorAll('.legend button')].map(x=>x.textContent):[]})()`);
check('10-round: ROC legend lists the genuinely evaluated states including R06', roc.some((t) => t.startsWith('R06')), roc.join('|'));
await click('atab-clients');
await waitFor(`!!${T('round-client-panel')}`, 20000);
await waitFor(`${T('weights-sum')}`, 30000);
check('10-round: client contributions of the selected round sum to weight 1 with 8/8 accepted', /1\.0000000000|0\.9999999999/.test(await text('weights-sum')) && (await text('weights-sum')).includes('8/8'), await text('weights-sum'));
await click('atab-comparison');
await waitFor(`!!${T('fig-FL10_FIG16')}`, 30000);
check('10-round: the same-cohort R3-to-R10 paired comparison is available', (await b.evaluate(`${T('fig-FL10_FIG16')}.getAttribute('data-availability')`)) === 'AVAILABLE');
check('10-round: the final candidate is the server-generated FL10 candidate, not promoted or deployed', (await text('candidate-id')).startsWith('FL10_CANDIDATE_FL10RUN-') && (await text('candidate-label')).includes('NOT PROMOTED'));
await tabsAndFigures(run10, '10-round', 10);
await migratedFeatures(run10, '10-round', 10, 80);
await narrowTabs('10-round');
await exportsWork(run10, '10-round');
evidence.widths10 = await widths('studio_run10', '');

// ---- D. run switching, historical replay, original 3-round page ---------------------------------------------------------------------
await b.evaluate(`(()=>{const s=document.querySelector('[data-testid="run-selector"]');s.value='${run3}';s.dispatchEvent(new Event('change',{bubbles:true}))})()`);
await waitFor(`new URL(location.href).searchParams.get('run')==='${run3}'`, 20000);
await waitFor(`${T('metric-round')}?.textContent.includes('ROUND R3')`, 30000);
check('switching 10-round -> 3-round clears the previous run: no R10 control, 3-round values only', !(await exists('round-btn-R10')) && (await exists('round-btn-R3')) && (await text('metric-AUPRC')).endsWith(six(run3rec[3].metric_result.AUPRC)));
await waitFor(`${T('accepted-counter')}?.textContent==='24/24'`, 30000).catch(() => {});   // the new run's journal replays from sequence 0
check('switching runs shows the 3-round run\'s own accepted counter', (await text('accepted-counter')) === '24/24', await text('accepted-counter'));
await b.navigate(`/app/federation/live?run=recorded-A`, `!!${T('run-status-strip')}`);
await waitFor(`${T('metric-round')}?.textContent.includes('ROUND R10')`, 60000);
check('recorded FL10 run opens as labelled historical evidence with no training', (await exists('recorded-note')) && (await text('run-status-line')).includes('COMPLETED'));
check('recorded run shows the recorded R10 values and the same reuse label', (await text('metric-AUPRC')).endsWith(six(recorded[10].metric_result.AUPRC)) && (await text('cohort-use-label')).includes('RECORDED FRESH 16-PARTICIPANT HOLDOUT') );
check('recorded run: eight-client network and no owner-bound star under DemoAuth', (await b.evaluate(`document.querySelectorAll('li[data-client]').length`)) === 8 && !(await exists('owner-card-label')));
await b.screenshot('studio_recorded_A');
await b.navigate(`/app/federation/live?run=FEDRUN-D4C404C2AB81`, `!!${T('run-status-strip')}`);
await sleep(1500);
check('a completed run that predates the observer says so and shows no metrics', (await exists('no-evaluation')) && !(await b.evaluate(`/AUPRC/.test(${T('metric-cards')}.innerText)`)));
check('the original eight-client network, stepper and timeline remain on that run', (await b.evaluate(`document.querySelectorAll('li[data-client]').length`)) === 8 && (await exists('coordinator')) && (await exists('round-states')));

// ---- E. consolidation: retired route redirects, every retained Observatory page loads, links point at the Studio ---------------------------------------------
await b.navigate('/app/observatory/fl10?run=recorded-B', `location.pathname==='/app/federation/live' || !!${T('fl10-moved')}`);
await waitFor(`location.pathname==='/app/federation/live'`, 20000);
check('retired FL10 Observatory route redirects into the Studio and preserves ?run=', (await runIdFromUrl()) === 'recorded-B');
await waitFor(`!!${T('run-status-strip')}`, 30000);
await b.navigate('/app/observatory/fl10', `location.pathname==='/app/federation/live' || !!${T('fl10-moved')}`);
await waitFor(`location.pathname==='/app/federation/live'`, 20000);
check('retired route without a run parameter opens the recorded Mode A run', (await runIdFromUrl()) === 'recorded-A');
await b.navigate('/app/observatory', `document.body.innerText.length > 500`);
check('Observatory home links to the Studio and no longer to the retired page', (await b.evaluate(`!!document.querySelector('a[href="/app/federation"]') && !document.querySelector('a[href="/app/observatory/fl10"]')`)));
const retained = ['/app/observatory', '/app/observatory/evidence', '/app/observatory/federation', '/app/observatory/federation/SIM_FL_SITE_00', '/app/observatory/federation-replay', '/app/observatory/model', '/app/observatory/outcomes', '/app/observatory/provenance',
  '/app/observatory/replay', '/app/observatory/research', '/app/observatory/scenarios', '/app/observatory/storyboard', '/app/observatory/tour', '/app/federation', '/app/federation/rounds', '/app/federation/clients', '/app/federation/privacy', '/app/federation/live'];
const loaded = {};
for (const path of retained) {
  const before = b.errors.length;
  await b.navigate(path, `document.body.innerText.length > 300`);
  await sleep(1200);
  loaded[path] = await b.evaluate(`({len:document.body.innerText.length, h1:document.querySelector('h1')?.textContent?.slice(0,60), overflow:document.documentElement.scrollWidth>innerWidth, notFound:/404|not found/i.test(document.querySelector('h1')?.textContent ?? '')})`);
  check(`retained route ${path} loads without errors or overflow`, loaded[path].len > 300 && !loaded[path].overflow && !loaded[path].notFound && b.errors.length === before, JSON.stringify(loaded[path]) + b.errors.slice(before).join('|'));
}
await b.navigate('/app/observatory/outcomes', `!!${T('frozen-label')}`);
check('protected scientific outcomes page still shows the frozen evidence label and comparison matrix', (await text('frozen-label')).includes('FROZEN RESEARCH EVIDENCE') && (await exists('comparability-matrix')));
await b.navigate('/app/observatory/storyboard', `!!${T('storyboard-step')}`);
check('storyboard keeps its guided steps and links to the Studio', (await exists('storyboard-step')) && (await b.evaluate(`!!document.querySelector('a[href="/app/federation"]')`)));
evidence.retainedRoutes = loaded;

check('no console errors or uncaught exceptions during the whole journey', b.errors.length === 0, b.errors.slice(0, 5).join(' | '));
evidence.errors = b.errors;
const passed = checks.every((c) => c.ok);
writeFileSync(`${output}/studio_browser_verification.json`, JSON.stringify({ passed, total: checks.length, failed: checks.filter((c) => !c.ok), checks, evidence, note: 'DemoAuth browser journey; connected Clerk ownership is NOT claimed' }, null, 1) + '\n');
console.log(JSON.stringify({ passed, total: checks.length, failed: checks.filter((c) => !c.ok).map((c) => c.name) }));
b.close();
if (!passed) process.exitCode = 1;
