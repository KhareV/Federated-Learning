// OBS-DIAG-001 documented accessibility assessment (real Chromium via CDP). Records observations per route; it is NOT a WCAG conformance audit.
//   node scripts/observatory_a11y_assessment.mjs <debugPort> <origin> <outJson>
import { writeFileSync } from 'node:fs';

const [, , debugPort, ORIGIN, OUT] = process.argv;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
class Cdp {
	constructor(url) { this.ws = new WebSocket(url); this.id = 0; this.pending = new Map(); this.handlers = []; this.ready = new Promise((res, rej) => { this.ws.onopen = res; this.ws.onerror = rej; });
		this.ws.onmessage = (m) => { const e = JSON.parse(m.data); if (e.id && this.pending.has(e.id)) { const { res, rej } = this.pending.get(e.id); this.pending.delete(e.id); e.error ? rej(new Error(JSON.stringify(e.error))) : res(e.result); } else if (e.method) for (const h of this.handlers) h(e.method, e.params); }; }
	send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
}
const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json();
const cdp = new Cdp(targets.find((t) => t.type === 'page').webSocketDebuggerUrl); await cdp.ready;
for (const d of ['Page', 'Runtime']) await cdp.send(`${d}.enable`);
const version = await (await fetch(`http://127.0.0.1:${debugPort}/json/version`)).json();
async function ev(expression) { const r = await cdp.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails).slice(0, 200)); return r.result.value; }
async function waitFor(expression, timeout = 90000) { const until = Date.now() + timeout; while (Date.now() < until) { let v = null; try { v = await ev(expression); } catch { /* navigating */ } if (v) return v; await sleep(200); } throw new Error(`timeout: ${expression.slice(0, 100)}`); }
const viewport = async (w, h = 900) => { await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w <= 480 }); await sleep(300); };
const goto = async (path) => { await cdp.send('Page.navigate', { url: ORIGIN + path }); await sleep(500); };
const key = async (k, code, vk) => { await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: k, code, windowsVirtualKeyCode: vk }); await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code, windowsVirtualKeyCode: vk }); };

// enter the offline DEMO workspace used by the development stack
await viewport(1440); await goto('/sign-in');
await waitFor(`document.body.innerText.includes('ENTER DEMO WORKSPACE')`);
await ev(`[...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'ENTER DEMO WORKSPACE')?.click()`);
await waitFor(`location.pathname === '/app'`);

const ROUTES = ['/app/observatory', '/app/observatory/federation', '/app/observatory/federation/SIM_FL_SITE_07', '/app/observatory/research', '/app/observatory/tour', '/app/observatory/evidence', '/app/observatory/model', '/app/observatory/provenance', '/app/observatory/scenarios', '/app/observatory/replay', '/app/observatory/federation-replay'];
const ready = { '/app/observatory': `!!document.querySelector('figure.signal')`, '/app/observatory/evidence': `!!document.querySelector('[data-testid="experiment-matrix"] tbody tr')`, '/app/observatory/model': `!!document.querySelector('[data-testid="explainability"] svg')`, '/app/observatory/provenance': `!!document.querySelector('[data-testid="boundaries"] li')`, '/app/observatory/scenarios': `!!document.querySelector('[data-testid="lab-window"]')`, '/app/observatory/federation': `document.querySelectorAll('.roster button').length === 8`, '/app/observatory/research': `!!document.querySelector('[data-testid="dataset-preprocessing"] article')` };

const LIB = `(() => {
const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
const parse = (s) => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(',').map((x) => parseFloat(x)); return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 }; };
const ratio = (a, b) => { const l1 = lum(a), l2 = lum(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
const bgOf = (el) => { let n = el; let acc = null; const stack = []; while (n && n.nodeType === 1) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { stack.push(c); if (c.a >= 1) break; } n = n.parentElement; } let base = [5, 10, 21]; if (!stack.length || stack[stack.length - 1].a < 1) { const b = parse(getComputedStyle(document.body).backgroundColor); if (b && b.a > 0) base = b.rgb; }
	for (let i = stack.length - 1; i >= 0; i--) { const c = stack[i]; base = base.map((v, k) => Math.round(c.rgb[k] * c.a + v * (1 - c.a))); } return base; };
const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
const name = (e) => (e.getAttribute('aria-label') || e.textContent || e.getAttribute('title') || '').trim();
return { lum, parse, ratio, bgOf, vis, name };
})()`;

// Negative control: the contrast checker must flag a deliberately low-contrast element (otherwise 'zero failures' would mean nothing).
await goto('/app/observatory/provenance'); await waitFor(`!!document.querySelector('h1')`); await sleep(800);
const control = await ev(`(() => { const L = ${LIB}; const el = document.createElement('p'); el.id = 'contrast-control'; el.textContent = 'low contrast control text'; el.style.cssText = 'color:#5a5a5a;background:#4a4a4a;position:absolute;top:0;left:0;z-index:99999'; document.querySelector('main').appendChild(el); const cs = getComputedStyle(el); const r = L.ratio(L.parse(cs.color).rgb, L.parse(cs.backgroundColor).rgb); el.remove(); return { ratio: +r.toFixed(2), flaggedAsFailing: r < 4.5 }; })()`);
const report = { browser: version.Browser, userAgent: version['User-Agent'], contrastNegativeControl: control, routes: [], criteria_tested: [] };
for (const route of ROUTES) {
	const r = { route };
	await viewport(1440); await goto(route);
	await waitFor(`!!document.querySelector('h1')`); if (ready[route]) await waitFor(ready[route]); await sleep(1500);
	// 2.4.2 title, 3.1.1 language, 1.3.1 structure
	r.structure = await ev(`({ title: document.title, lang: document.documentElement.lang, h1: document.querySelectorAll('h1').length, main: document.querySelectorAll('main').length, headingOrder: [...document.querySelectorAll('h1,h2,h3')].map((h) => +h.tagName[1]).every((lvl, i, a) => i === 0 || lvl - a[i - 1] <= 1) })`);
	// 1.4.3 contrast of visible text
	r.contrast = await ev(`(() => { const L = ${LIB}; const bad = []; let checked = 0; const seen = new Set();
		for (const el of document.querySelectorAll('main *, aside *, header *')) { if (!el.childNodes.length) continue; const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim().length > 1); if (!own.length || !L.vis(el)) continue; const cs = getComputedStyle(el); const fg = L.parse(cs.color); if (!fg) continue; const bg = L.bgOf(el); const fgRgb = fg.a < 1 ? fg.rgb.map((v, k) => Math.round(v * fg.a + bg[k] * (1 - fg.a))) : fg.rgb; const ratio = L.ratio(fgRgb, bg); const size = parseFloat(cs.fontSize); const large = size >= 24 || (size >= 18.66 && parseInt(cs.fontWeight) >= 700); const need = large ? 3 : 4.5; checked++; if (ratio < need) { const k = el.tagName + '|' + cs.color + '|' + bg.join(','); if (!seen.has(k)) { seen.add(k); bad.push({ text: own[0].textContent.trim().slice(0, 40), ratio: +ratio.toFixed(2), need, color: cs.color, bg: bg.join(','), size }); } } }
		return { checked, failingDistinct: bad.length, worst: bad.sort((a, b) => a.ratio - b.ratio).slice(0, 6) }; })()`);
	// 1.1.1 chart/graphic alternatives, 4.1.2 names, 3.3.2 labels, 2.5.8 target size
	r.semantics = await ev(`(() => { const L = ${LIB}; const svgs = [...document.querySelectorAll('svg')].filter((s) => L.vis(s) && s.getAttribute('aria-hidden') !== 'true' && !s.closest('button,a,summary'));
		const svgNoName = svgs.filter((s) => !(s.getAttribute('aria-label') || s.querySelector('title') || s.closest('figure')?.querySelector('figcaption'))).length;
		const fields = [...document.querySelectorAll('select,input,textarea')].filter(L.vis); const unlabelled = fields.filter((f) => !(f.getAttribute('aria-label') || (f.id && document.querySelector('label[for="' + f.id + '"]')) || f.closest('label'))).length;
		const unnamed = [...document.querySelectorAll('button,a[href],summary,[role=button]')].filter((e) => L.vis(e) && !L.name(e)).length;
		const smallEls = [...document.querySelectorAll('main button, main a, main summary, main select, main input:not([type=range])')].filter((e) => { if (!L.vis(e) || e.closest('label') && e.tagName === 'INPUT') return false; const r = e.getBoundingClientRect(); return r.height < 24 || r.width < 24; }); const small = smallEls.length;
		const sliders = [...document.querySelectorAll('input[type=range]')].filter(L.vis); const sliderNoValueText = sliders.filter((s) => !(s.getAttribute('aria-valuetext') || s.closest('label') || s.getAttribute('aria-label'))).length;
		const chartsWithTextSummary = svgs.filter((s) => { const fig = s.closest('figure,section,article'); return !!(fig && fig.innerText && fig.innerText.replace(/\\s+/g, ' ').length > 60); }).length;
		return { svgCount: svgs.length, svgNoName, chartsWithTextSummary, fields: fields.length, unlabelled, unnamedControls: unnamed, targetsUnder24px: small, smallTargetNames: smallEls.slice(0, 5).map((e) => L.name(e).slice(0, 30)), sliders: sliders.length, sliderNoValueText, tablesWithoutHeaders: [...document.querySelectorAll('table')].filter((t) => !t.querySelector('th')).length }; })()`);
	// 2.1.1 / 2.1.2 / 2.4.3 / 2.4.7 / 2.4.11 keyboard walk with real Tab key events
	await ev(`document.activeElement && document.activeElement.blur(); window.scrollTo(0,0)`);
	const stops = []; const seenIds = new Set(); let trap = false;
	for (let i = 0; i < 90; i++) {
		await key('Tab', 'Tab', 9); await sleep(25);
		const s = await ev(`(() => { const L = ${LIB}; const a = document.activeElement; if (!a || a === document.body) return { body: true }; const cs = getComputedStyle(a); const r = a.getBoundingClientRect(); const hit = document.elementFromPoint(Math.min(innerWidth - 1, Math.max(0, r.x + r.width / 2)), Math.min(innerHeight - 1, Math.max(0, r.y + r.height / 2)));
			return { id: a.tagName + ':' + L.name(a).slice(0, 30) + ':' + Math.round(r.x) + ',' + Math.round(a.getBoundingClientRect().y + scrollY), y: r.y + scrollY, indicator: (cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow && cs.boxShadow !== 'none') || a.matches(':focus-visible'), obscured: !(hit === a || a.contains(hit) || (hit && hit.contains(a))), inViewport: r.bottom > 0 && r.top < innerHeight }; })()`);
		if (s.body) { if (stops.length > 3) break; continue; }
		if (seenIds.has(s.id)) { trap = false; break; }
		seenIds.add(s.id); stops.push(s);
	}
	const focusables = await ev(`[...document.querySelectorAll('main button:not([disabled]), main a[href], main select, main input:not([disabled]), main summary, main [tabindex="0"]')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; }).length`);
	const inversions = stops.filter((s, i) => i > 0 && s.y + 40 < stops[i - 1].y).length;
	r.keyboard = { tabStopsReached: stops.length, focusableInMain: focusables, keyboardTrapSuspected: trap, noIndicator: stops.filter((s) => !s.indicator).length, obscuredWhenFocused: stops.filter((s) => s.obscured && s.inViewport).length, orderInversions: inversions };
	// 1.4.10 reflow at 320 css px; 1.4.12 text spacing
	await viewport(320, 700); await sleep(500);
	r.reflow320 = await ev(`({ horizontalScroll: document.documentElement.scrollWidth > innerWidth + 1, scrollWidth: document.documentElement.scrollWidth })`);
	await ev(`(() => { const s = document.createElement('style'); s.id = 'a11y-spacing'; s.textContent = '* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; } p { margin-bottom: 2em !important; }'; document.head.appendChild(s); })()`); await sleep(400);
	r.textSpacing = await ev(`({ horizontalScroll: document.documentElement.scrollWidth > innerWidth + 1 })`);
	await ev(`document.getElementById('a11y-spacing')?.remove()`);
	// 2.3.3 / reduced motion
	await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] }); await sleep(400);
	r.reducedMotion = await ev(`({ matches: matchMedia('(prefers-reduced-motion: reduce)').matches, runningAnimations: document.getAnimations().filter((a) => a.playState === 'running' && (a.effect?.getTiming().iterations === Infinity)).length })`);
	await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
	report.routes.push(r);
}
// focus management on SPA navigation: after clicking an internal link, focus should not be lost into a removed node
await viewport(1440); await goto('/app/observatory'); await waitFor(`!!document.querySelector('figure.signal')`);
await ev(`[...document.querySelectorAll('a')].find((a) => a.getAttribute('href') === '/app/observatory/tour')?.click()`); await sleep(1200);
report.focusAfterNavigation = await ev(`({ path: location.pathname, activeTag: document.activeElement?.tagName, activeIsBody: document.activeElement === document.body, activeIsHeading: document.activeElement === document.querySelector('h1'), h1: document.querySelector('h1')?.textContent })`);
const sum = (f) => report.routes.reduce((a, r) => a + f(r), 0);
report.summary = { routes: report.routes.length, contrastFailingDistinctTotal: sum((r) => r.contrast.failingDistinct), contrastChecked: sum((r) => r.contrast.checked), svgNoName: sum((r) => r.semantics.svgNoName), unlabelledFields: sum((r) => r.semantics.unlabelled), unnamedControls: sum((r) => r.semantics.unnamedControls),
	targetsUnder24px: sum((r) => r.semantics.targetsUnder24px), tablesWithoutHeaders: sum((r) => r.semantics.tablesWithoutHeaders), noFocusIndicator: sum((r) => r.keyboard.noIndicator), focusObscured: sum((r) => r.keyboard.obscuredWhenFocused), reflow320Failures: report.routes.filter((r) => r.reflow320.horizontalScroll).length,
	textSpacingFailures: report.routes.filter((r) => r.textSpacing.horizontalScroll).length, reducedMotionInfiniteAnimations: sum((r) => r.reducedMotion.runningAnimations), routesWithoutSingleH1: report.routes.filter((r) => r.structure.h1 !== 1).length, routesWithoutLang: report.routes.filter((r) => !r.structure.lang).length };
report.criteria_tested = ['1.1.1 Non-text Content (chart names and text summaries)', '1.3.1 Info and Relationships (headings, table headers, labels)', '1.4.3 Contrast (Minimum) (computed text vs effective background)', '1.4.10 Reflow (320 CSS px)', '1.4.12 Text Spacing (overflow only)', '2.1.1 Keyboard (real Tab key events)', '2.1.2 No Keyboard Trap (heuristic)', '2.3.3-style motion: prefers-reduced-motion respected for infinite animations', '2.4.2 Page Titled', '2.4.3 Focus Order (vertical-order heuristic)', '2.4.7 Focus Visible', '2.4.11 Focus Not Obscured (Minimum)', '2.5.8 Target Size (Minimum) 24x24', '3.1.1 Language of Page', '3.3.2 Labels or Instructions', '4.1.2 Name, Role, Value (names and states, static check)'];
report.not_tested = ['1.4.11 Non-text Contrast of graphics and component boundaries', '1.2.x time-based media (none present)', '2.4.5 multiple ways, 3.2.x consistency, 3.3.x error handling beyond labels', 'screen-reader output with real assistive technology (VoiceOver/NVDA/JAWS)', 'Firefox and WebKit engines (not available in this environment)'];
writeFileSync(OUT, JSON.stringify(report, null, 1));
await cdp.send('Browser.close').catch(() => {});
process.exit(0);
