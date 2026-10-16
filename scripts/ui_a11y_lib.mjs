// Non-hardware accessibility/semantics/network audit of every product route (real Chrome, real Clerk session).
// Pure measurement: nothing here changes the application. Findings are structured so a defect ledger can be built without hand-typed numbers.
import { writeFileSync } from 'node:fs';

export const ROUTES = ['/app', '/app/device', '/app/monitoring', '/app/history', '/app/federation', '/app/federation/live', '/app/federation/clients', '/app/federation/rounds', '/app/federation/privacy',
	'/app/models', '/app/research/ml', '/app/research/fl', '/app/system', '/app/about', '/app/observatory', '/app/observatory/evidence', '/app/observatory/federation', '/app/observatory/fl10',
	'/app/observatory/model', '/app/observatory/outcomes', '/app/observatory/provenance', '/app/observatory/replay', '/app/observatory/scenarios', '/app/observatory/storyboard', '/app/observatory/tour',
	'/app/federation/live?run=recorded-A', '/app/observatory/federation/SIM_FL_SITE_00', '/app/history/NO-SUCH-SESSION'];

// Describes the element that currently has keyboard focus and WHY it might not be usable (hidden / clipped / obscured / outside the viewport after the browser's own scroll).
const FOCUS_INFO = `(() => {
	const e = document.activeElement; if (!e || e === document.body || e === document.documentElement) return null;
	const r = e.getBoundingClientRect(), c = getComputedStyle(e), vw = innerWidth, vh = innerHeight;
	const chain = []; for (let p = e; p; p = p.parentElement) chain.push(p);
	const closedDetails = chain.find((p) => p.tagName === 'DETAILS' && !p.open && !(e.tagName === 'SUMMARY' && e.parentElement === p)) ?? null;
	const hiddenAncestor = chain.find((p) => { const s = getComputedStyle(p); return s.display === 'none' || s.visibility === 'hidden' || p.hasAttribute('hidden') || p.getAttribute('aria-hidden') === 'true' || p.hasAttribute('inert'); }) ?? null;
	let clippedBy = null; for (const p of chain.slice(1)) { const s = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(s.overflowX + s.overflowY)) { const pr = p.getBoundingClientRect(); if (r.right > pr.right + 1 || r.left < pr.left - 1 || r.bottom > pr.bottom + 1 || r.top < pr.top - 1) { clippedBy = (p.tagName.toLowerCase() + '.' + String(p.className).split(' ')[0]).slice(0, 50); break; } } }
	const header = document.querySelector('header, .topbar, [data-testid="topbar"]'); const hb = header ? header.getBoundingClientRect() : null;
	const isSkipLink = e.tagName === 'A' && /skip/i.test(e.className + ' ' + (e.innerText || ''));
	const ownSticky = isSkipLink || chain.some((p) => { const ps = getComputedStyle(p).position; return ps === 'sticky' || ps === 'fixed'; });   // the sticky/fixed bars' own controls are not 'obscured by' them
	const sticky = hb && getComputedStyle(header).position !== 'static' && !ownSticky ? hb.bottom : 0;
	const ring = (c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0) || (c.boxShadow && c.boxShadow !== 'none');
	return { tag: e.tagName.toLowerCase(), role: e.getAttribute('role'), name: (e.getAttribute('aria-label') || e.innerText || e.value || e.getAttribute('title') || '').trim().replace(/\\s+/g, ' ').slice(0, 48),
		top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height),
		inViewport: r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw, fullyInViewport: r.top >= 0 && r.bottom <= vh && r.left >= 0 && r.right <= vw,
		underSticky: sticky > 0 && r.top < sticky - 1 && r.bottom > 0, ring: !!ring, closedDetails: closedDetails ? 'details' : null, hiddenAncestor: hiddenAncestor ? hiddenAncestor.tagName.toLowerCase() : null,
		clippedBy, tabindex: e.getAttribute('tabindex'), inMain: !!e.closest('main'), scrollY: Math.round(scrollY), mainScroll: (() => { const m = document.querySelector('main'); return m ? Math.round(m.scrollTop) : 0; })(), smooth: getComputedStyle(document.documentElement).scrollBehavior };
})()`;

const SEMANTICS = `(() => {
	const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
	const name = (e) => (e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') && document.getElementById(e.getAttribute('aria-labelledby'))?.textContent || e.textContent || e.getAttribute('title') || '').trim();
	const heads = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].filter(vis);
	const level = (h) => Number(h.getAttribute('aria-level')) || Number(h.tagName[1]);
	const headingOutline = heads.map(level);
	const skips = heads.map((h, i) => (i > 0 && level(h) - level(heads[i - 1]) > 1 ? { at: (h.textContent || '').trim().slice(0, 40), from: level(heads[i - 1]), to: level(h) } : null)).filter(Boolean);
	const emptyHeadings = heads.filter((h) => !(h.textContent || '').trim()).length;
	const svgs = [...document.querySelectorAll('svg')].filter(vis).filter((s) => { const r = s.getBoundingClientRect(); return r.width >= 60 && r.height >= 40; });
	const svgNoName = svgs.filter((s) => !((s.getAttribute('role') === 'img' || s.getAttribute('role') === 'group') && (s.getAttribute('aria-label') || s.querySelector('title'))) && s.getAttribute('aria-hidden') !== 'true' && !s.closest('[aria-hidden="true"]') && !s.closest('figure[aria-label], [role=img][aria-label]')).slice(0, 6).map((s) => (s.getAttribute('class') || s.parentElement?.className || '').toString().slice(0, 40) + ' ' + Math.round(s.getBoundingClientRect().width) + 'x' + Math.round(s.getBoundingClientRect().height));
	const tables = [...document.querySelectorAll('table')].filter(vis);
	const tablesNoCaption = tables.filter((t) => !t.querySelector('caption') && !t.getAttribute('aria-label') && !t.getAttribute('aria-labelledby') && !t.closest('[role=region][aria-label]')).length;
	const thNoScope = [...document.querySelectorAll('th')].filter((t) => vis(t) && !t.getAttribute('scope')).length;
	const controls = [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(vis);
	const controlsNoLabel = controls.filter((c) => !(c.labels && c.labels.length) && !c.getAttribute('aria-label') && !c.getAttribute('aria-labelledby') && !c.getAttribute('title')).slice(0, 5).map((c) => c.tagName.toLowerCase() + '[' + (c.getAttribute('type') || c.name || c.id || '') + ']');
	const interactive = [...document.querySelectorAll('button, a[href], [role=button], summary')].filter(vis);
	const unnamed = interactive.filter((b) => !name(b)).slice(0, 5).map((b) => b.outerHTML.slice(0, 90));
	const generic = interactive.filter((b) => /^(click here|here|more|link|button)$/i.test(name(b))).length;
	const regions = [...document.querySelectorAll('[role=region], section[aria-label], section[aria-labelledby]')].length;
	const live = document.querySelectorAll('[aria-live], [role=status], [role=alert]').length;
	const posTab = [...document.querySelectorAll('[tabindex]')].filter((e) => Number(e.getAttribute('tabindex')) > 0).length;
	const scrollRegionsNoName = [...document.querySelectorAll('[tabindex="0"]')].filter((e) => vis(e) && e.scrollWidth > e.clientWidth + 1 && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby') && !e.getAttribute('role')).length;
	const dupIds = (() => { const seen = {}; let n = 0; document.querySelectorAll('[id]').forEach((e) => { seen[e.id] = (seen[e.id] || 0) + 1; if (seen[e.id] === 2) n++; }); return n; })();
	const imgNoAlt = [...document.querySelectorAll('img')].filter((i) => vis(i) && !i.hasAttribute('alt')).length;
	const tiny = {}; [...document.querySelectorAll('body *')].filter((e) => vis(e) && !e.closest('svg') && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 10.5).forEach((e) => { const k = e.tagName.toLowerCase() + '@' + getComputedStyle(e).fontSize; tiny[k] = (tiny[k] || 0) + 1; });
	const chartStops = [...document.querySelectorAll('svg')].map((g) => g.querySelectorAll('[tabindex="0"]').length);
	const chartPointsFocusable = document.querySelectorAll('svg [tabindex]').length;
	return { smallHtmlText: Object.values(tiny).reduce((a, b) => a + b, 0), smallHtmlTextBreakdown: Object.entries(tiny).sort((a, b) => b[1] - a[1]).slice(0, 6), chartTabStopsMax: Math.max(0, ...chartStops), chartTabStopsTotal: chartStops.reduce((a, b) => a + b, 0), chartsWithPoints: chartStops.filter((n) => n > 0).length, chartPointsFocusable, lang: document.documentElement.lang || null, title: document.title, h1: heads.filter((h) => h.tagName === 'H1').length, headingOutline, headingSkips: skips, emptyHeadings,
		landmarks: { main: document.querySelectorAll('main,[role=main]').length, nav: document.querySelectorAll('nav,[role=navigation]').length, banner: document.querySelectorAll('header,[role=banner]').length, contentinfo: document.querySelectorAll('footer,[role=contentinfo]').length },
		skipLink: !!document.querySelector('a.skip, a[href="#main-content"]'), svgCharts: svgs.length, svgNoName, tables: tables.length, tablesNoCaption, thNoScope, controls: controls.length, controlsNoLabel,
		interactive: interactive.length, unnamedInteractive: unnamed, genericLinkText: generic, regions, liveRegions: live, positiveTabindex: posTab, scrollRegionsNoName, duplicateIds: dupIds, imgNoAlt };
})()`;

async function tabJourney(cdp, ev, sleep, max) {
	await ev(`document.activeElement && document.activeElement.blur && document.activeElement.blur(); window.scrollTo(0, 0); const m = document.querySelector('main'); if (m) m.scrollTop = 0;`);
	const stops = []; let first = null;
	for (let i = 0; i < max; i++) {
		await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
		await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
		// wait for the browser's own focus-into-view scroll to SETTLE (html uses smooth scrolling): measure the resting position, not mid-animation
		let prev = -1;
		for (let k = 0; k < 30; k++) { await sleep(50); const pos = await ev(`Math.round(scrollY) + ':' + Math.round(document.querySelector('main')?.scrollTop ?? 0)`); if (pos === prev) break; prev = pos; }
		const info = await ev(FOCUS_INFO);
		if (!info) { if (stops.length > 3) break; continue; }
		const key = `${info.tag}|${info.name}|${info.left}|${info.top + info.scrollY}`;
		if (first === key) break;
		first ??= key;
		stops.push(info);
	}
	return stops;
}

export async function runA11y({ cdp, ev, goto, events, sleep, out, routes = ROUTES, viewports, tabMax = 90 }) {
	const report = [];
	for (const vp of viewports) {
		await cdp.send('Emulation.setDeviceMetricsOverride', { width: vp.width, height: vp.height, deviceScaleFactor: 1, mobile: vp.mobile });
		for (const route of routes) {
			events.length = 0;
			const entry = { route, viewport: vp.name };
			try {
				await goto(route); await sleep(2600);
				entry.semantics = await ev(SEMANTICS);
				entry.httpStatus = await ev(`fetch(location.href, { cache: 'no-store' }).then((r) => r.status).catch(() => null)`);
				const stops = await tabJourney(cdp, ev, sleep, tabMax);
				entry.focus = {
					stops: stops.length, noRing: stops.filter((s) => !s.ring).length, hidden: stops.filter((s) => s.closedDetails || s.hiddenAncestor).map((s) => ({ name: s.name, tag: s.tag, closedDetails: s.closedDetails, hidden: s.hiddenAncestor })),
					outside: stops.filter((s) => !s.inViewport).map((s) => ({ tag: s.tag, name: s.name, top: s.top, bottom: s.bottom, left: s.left, right: s.right, clippedBy: s.clippedBy, scrollY: s.scrollY, mainScroll: s.mainScroll })),
					partlyOutside: stops.filter((s) => s.inViewport && !s.fullyInViewport).length, underSticky: stops.filter((s) => s.underSticky).map((s) => ({ tag: s.tag, name: s.name, top: s.top })),
					tooSmall: stops.filter((s) => (s.w < 24 || s.h < 24) && s.tag !== 'a').map((s) => ({ tag: s.tag, name: s.name, w: s.w, h: s.h })).slice(0, 6),
					first: stops.slice(0, 3).map((s) => s.name), outsideMain: stops.filter((s) => !s.inMain).length
				};
				const consoleMsgs = events.filter((e) => e.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(e.params.type)).map((e) => `${e.params.type}: ${(e.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 140)}`);
				const logs = events.filter((e) => e.method === 'Log.entryAdded' && ['error', 'warning'].includes(e.params.entry.level)).map((e) => `${e.params.entry.level}: ${e.params.entry.text.slice(0, 140)} ${e.params.entry.url ? '[' + String(e.params.entry.url).replace(/^https?:\/\/[^/]+/, '').slice(0, 70) + ']' : ''}`);
				const exceptions = events.filter((e) => e.method === 'Runtime.exceptionThrown').map((e) => (e.params.exceptionDetails?.exception?.description || e.params.exceptionDetails?.text || 'exception').slice(0, 160));
				entry.console = [...new Set([...consoleMsgs, ...logs, ...exceptions])].slice(0, 8);
				const byId = new Map(); for (const e of events) if (e.method === 'Network.requestWillBeSent') byId.set(e.params.requestId, e.params.request.url);
				entry.failedRequests = events.filter((e) => e.method === 'Network.responseReceived' && e.params.response.status >= 400).map((e) => `${e.params.response.status} ${e.params.type} ${e.params.response.url.replace(/^https?:\/\/[^/]+/, '').slice(0, 90)}`);
				entry.networkErrors = events.filter((e) => e.method === 'Network.loadingFailed' && !e.params.canceled).map((e) => `${e.params.errorText} ${(byId.get(e.params.requestId) || '').replace(/^https?:\/\/[^/]+/, '').slice(0, 80)}`);
				entry.externalHosts = [...new Set([...byId.values()].map((u) => { try { return new URL(u).host; } catch { return ''; } }).filter((h) => h && !/^(127\.0\.0\.1|localhost)(:|$)/.test(h)))].slice(0, 6);
			} catch (error) { entry.error = String(error).slice(0, 220); }
			report.push(entry);
		}
	}
	writeFileSync(out, JSON.stringify({ report }, null, 1));
	return report;
}
