// UI tour library: every product route at desktop and phone width (layout/density facts + a full-page screenshot per route/viewport).
import { writeFileSync } from 'node:fs';
export const ROUTES = ['/app', '/app/device', '/app/monitoring', '/app/history', '/app/federation', '/app/federation/live', '/app/federation/clients', '/app/federation/rounds', '/app/federation/privacy',
	'/app/models', '/app/research/ml', '/app/research/fl', '/app/system', '/app/about', '/app/observatory', '/app/observatory/evidence', '/app/observatory/federation', '/app/observatory/fl10', '/app/observatory/model',
	'/app/observatory/outcomes', '/app/observatory/provenance', '/app/observatory/replay', '/app/observatory/scenarios', '/app/observatory/storyboard', '/app/observatory/tour', '/app/observatory/federation-replay', '/app/observatory/external-check', '/app/demo', ];
const VIEWPORTS = [{ name: 'desktop', width: 1440, height: 900, mobile: false }, { name: 'laptop', width: 1024, height: 768, mobile: false }, { name: 'tablet', width: 768, height: 1024, mobile: true }, { name: 'phone', width: 390, height: 844, mobile: true }];
const METRICS = `(() => {
	const vw = window.innerWidth, vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
	const text = (document.querySelector('main') ?? document.body).innerText || '';
	const words = text.split(/\\s+/).filter(Boolean).length;
	const paras = [...document.querySelectorAll('p, li, dd')].filter(vis).map((p) => ({ n: (p.innerText || '').split(/\\s+/).filter(Boolean).length, t: (p.innerText || '').slice(0, 90) }));
	const long = paras.filter((p) => p.n >= 45).sort((a, b) => b.n - a.n).slice(0, 5);
	const over = [...document.querySelectorAll('body *')].filter((e) => vis(e) && e.getBoundingClientRect().right > vw + 2 && !e.closest('svg, [aria-hidden=true], .sr-only, pre, table, [class*=scroll], [tabindex="0"]')).slice(0, 6).map((e) => e.tagName.toLowerCase() + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : '') + ' ' + Math.round(e.getBoundingClientRect().right));
	const tiny = [...document.querySelectorAll('body *')].filter((e) => vis(e) && e.childNodes.length && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 10.5).length;
	const tinyBy = {}; [...document.querySelectorAll('body *')].filter((e) => vis(e) && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 10.5).forEach((e) => { const k = e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.split(' ').filter((c) => !c.startsWith('svelte-'))[0] : '') + '@' + getComputedStyle(e).fontSize; tinyBy[k] = (tinyBy[k] || 0) + 1; });
	const unnamed = [...document.querySelectorAll('button, a[href], input, select')].filter((e) => vis(e) && !(e.getAttribute('aria-label') || e.getAttribute('title') || (e.innerText || '').trim() || e.labels?.length || e.getAttribute('aria-labelledby'))).length;
	const h1 = document.querySelectorAll('h1').length;
	const unnamedSamples = [...document.querySelectorAll('button, a[href], input, select')].filter((e) => vis(e) && !(e.getAttribute('aria-label') || e.getAttribute('title') || (e.innerText || '').trim() || e.labels?.length || e.getAttribute('aria-labelledby'))).slice(0, 6).map((e) => e.outerHTML.slice(0, 140));
	const caps = [...document.querySelectorAll('body *')].filter((e) => vis(e) && e.children.length === 0 && /^[A-Z0-9 ·\\-—:,.()/%]{40,}$/.test((e.textContent || '').trim())).length;
	const heads = [...document.querySelectorAll('h1,h2,h3,h4')].filter(vis).map((h) => Number(h.tagName[1]));
	const headingSkips = heads.reduce((n, h, i) => n + (i > 0 && h - heads[i - 1] > 1 ? 1 : 0), 0);
	const landmarks = { main: document.querySelectorAll('main, [role=main]').length, nav: document.querySelectorAll('nav, [role=navigation]').length, skipLink: !!document.querySelector('a[href="#main"], a[href="#content"], .skip-link, a.skip') };
	const pageText = (document.querySelector('main') ?? document.body).innerText.replace(/[ \\t]+/g, ' ').replace(/\\n{2,}/g, '\\n').slice(0, 3500);
	return { text: pageText, headingSkips, landmarks, path: location.pathname + location.search, scrollWidth: document.documentElement.scrollWidth, innerWidth: vw, horizontalOverflow: document.documentElement.scrollWidth > vw + 1, words, paragraphs: paras.length, longParagraphs: long, overflowing: over, tinyTextElements: tiny, tinyBreakdown: Object.entries(tinyBy).sort((a, b) => b[1] - a[1]).slice(0, 8), unnamedControls: unnamed, unnamedSamples, h1Count: h1, allCapsLongLines: caps, title: document.title, docHeight: document.documentElement.scrollHeight };
})()`;

const FOCUS_INFO = `(() => { const e = document.activeElement; if (!e || e === document.body) return null; const c = getComputedStyle(e); const r = e.getBoundingClientRect();
	const ring = (c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0) || (c.boxShadow && c.boxShadow !== 'none');
	return { tag: e.tagName.toLowerCase(), name: (e.getAttribute('aria-label') || e.innerText || e.value || e.getAttribute('title') || '').trim().slice(0, 40), ring: !!ring, inView: r.bottom > 0 && r.top < innerHeight, size: [Math.round(r.width), Math.round(r.height)] }; })()`;
async function keyboardProbe(cdp, ev, sleep, presses = 30) {
	await ev(`document.activeElement && document.activeElement.blur && document.activeElement.blur(); window.scrollTo(0, 0)`);
	const stops = [];
	for (let i = 0; i < presses; i++) {
		await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
		await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 });
		await sleep(40);
		const info = await ev(FOCUS_INFO);
		if (info) stops.push(info);
	}
	return { stops: stops.length, noRing: stops.filter((x) => !x.ring).length, smallTargets: stops.filter((x) => (x.size[0] < 24 || x.size[1] < 24) && x.tag !== 'a').length, offscreen: stops.filter((x) => !x.inView).length, firstFew: stops.slice(0, 6).map((x) => x.name) };
}
export async function runTour({ cdp, ev, goto, events, sleep, shots, out, extraRoutes = [] }) {
	const routes = [...ROUTES, ...extraRoutes];
	const report = [];
	for (const vp of VIEWPORTS) {
		await cdp.send('Emulation.setDeviceMetricsOverride', { width: vp.width, height: vp.height, deviceScaleFactor: 1, mobile: vp.mobile });
		for (const route of routes) {
			events.length = 0;
			let entry = { route, viewport: vp.name };
			try {
				await goto(route); await sleep(3200);
				entry = { ...entry, ...(await ev(METRICS)) };
			entry.httpStatus = await ev(`fetch(location.href, { cache: 'no-store' }).then((r) => r.status).catch(() => null)`);
			if (vp.name === 'desktop' || vp.name === 'phone') entry.keyboard = await keyboardProbe(cdp, ev, sleep, 25);
				const errs = events.filter((e) => (e.method === 'Runtime.exceptionThrown') || (e.method === 'Log.entryAdded' && e.params.entry.level === 'error') || (e.method === 'Runtime.consoleAPICalled' && e.params.type === 'error'));
				entry.failedRequests = events.filter((e) => e.method === 'Network.responseReceived' && e.params.response.status >= 400).slice(0, 6).map((e) => e.params.response.status + ' ' + e.params.response.url.replace(/^https?:\/\/[^/]+/, '').slice(0, 110));
			entry.externalHosts = [...new Set(events.filter((e) => e.method === 'Network.requestWillBeSent').map((e) => { try { return new URL(e.params.request.url).host; } catch { return ''; } }).filter((h) => h && !/^(127\.0\.0\.1|localhost)(:|$)/.test(h)))].slice(0, 8);
			entry.consoleErrors = errs.slice(0, 4).map((e) => (e.params.entry?.text ?? e.params.exceptionDetails?.text ?? e.params.args?.[0]?.value ?? 'error').toString().slice(0, 160));
				const h = Math.min(Math.max(entry.docHeight || vp.height, vp.height), 9000);
				await cdp.send('Emulation.setDeviceMetricsOverride', { width: vp.width, height: h, deviceScaleFactor: 1, mobile: vp.mobile });
				await sleep(400);
				const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
				writeFileSync(`${shots}/${vp.name}_${route.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'root'}.png`, Buffer.from(shot.data, 'base64'));
				await cdp.send('Emulation.setDeviceMetricsOverride', { width: vp.width, height: vp.height, deviceScaleFactor: 1, mobile: vp.mobile });
			} catch (error) { entry.error = String(error).slice(0, 200); }
			report.push(entry);
		}
	}
	writeFileSync(out, JSON.stringify({ signed_in: true, report }, null, 1));
		return report;
}
