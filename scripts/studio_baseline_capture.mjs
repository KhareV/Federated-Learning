// Phase-1 reference capture of the ORIGINAL Federation Studio (before any change): entry page, a real 3-round run, live page, client selection.
import { writeFileSync } from 'node:fs';
import { connect, sleep } from './studio_cdp.mjs';

const [, , debugPort, origin, output] = process.argv;
const b = await connect(debugPort, origin, output);
const report = { origin, captured: {}, widths: [1440, 1024, 768, 390] };
await b.viewport(1440);
await b.demoSignIn();
await b.navigate('/app/federation', `!!document.querySelector('[data-testid="cfg-submit"]')`);
for (const w of report.widths) { await b.viewport(w); await sleep(300); await b.screenshot(`entry_${w}`); report.captured[`entry_${w}`] = await b.evaluate(`({overflow:document.documentElement.scrollWidth>innerWidth})`); }
await b.viewport(1440);
if (process.env.BASELINE_RUN) {
  await b.navigate(`/app/federation/live?run=${process.env.BASELINE_RUN}`, `!!document.querySelector('[data-testid="run-status"]')`);
} else {
  await b.navigate('/app/federation', `!!document.querySelector('[data-testid="cfg-submit"]')`);
  await b.wait(`!document.querySelector('[data-testid="cfg-submit"]').disabled`, 120000);
  await b.evaluate(`document.querySelector('[data-testid="cfg-submit"]').click()`);
  await b.wait(`location.pathname==='/app/federation/live'`, 60000);
}
report.run = await b.evaluate(`new URL(location.href).searchParams.get('run')`);
// mid-run capture, then wait for completion
await sleep(4000);
await b.screenshot('live_midrun_1440');
await b.wait(`document.querySelector('[data-testid="run-status"]')?.innerText.includes('COMPLETED')`, 600000);
for (const w of report.widths) {
  await b.viewport(w); await sleep(500);
  await b.screenshot(`live_completed_${w}`);
  report.captured[`live_${w}`] = await b.evaluate(`({overflow:document.documentElement.scrollWidth>innerWidth, clients:document.querySelectorAll('li[data-client]').length, status:document.querySelector('[data-testid="run-status"]')?.innerText, star:document.body.innerText.includes('MY EDGE CLIENT')||document.body.innerText.includes('★')})`);
}
await b.viewport(1440);
const firstClient = await b.evaluate(`(()=>{const e=document.querySelector('li[data-client] button.node');if(e){e.click();return e.getAttribute('aria-label')}return null})()`);
await sleep(500);
await b.screenshot('live_client_selected_1440');
report.firstClientTestId = firstClient;
report.errors = b.errors;
writeFileSync(`${output}/baseline_report.json`, JSON.stringify(report, null, 2) + '\n');
b.close();
console.log(JSON.stringify(report));
