// @vitest-environment jsdom
// A chart is ONE tab stop; arrow keys move between its points; Tab leaves the chart instead of walking every point.
import { describe, expect, it } from 'vitest';
import { chartNav } from '../chart-nav';

function chart(points = 5): { svg: SVGSVGElement; pts: SVGElement[]; destroy: () => void } {
	document.body.innerHTML = '<button id="before">before</button><svg id="c"></svg><button id="after">after</button>';
	const svg = document.getElementById('c') as unknown as SVGSVGElement;
	for (let i = 0; i < points; i++) {
		const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
		c.setAttribute('tabindex', '0');
		c.setAttribute('aria-label', `point ${i}`);
		svg.appendChild(c);
	}
	const action = chartNav(svg);
	return { svg, pts: [...svg.querySelectorAll<SVGElement>('circle')], destroy: action.destroy };
}
const key = (el: Element, k: string) => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));

describe('chart keyboard model', () => {
	it('exposes exactly one tab stop per chart', () => {
		const { pts } = chart();
		expect(pts.filter((p) => p.getAttribute('tabindex') === '0')).toHaveLength(1);
		expect(pts.filter((p) => p.getAttribute('tabindex') === '-1')).toHaveLength(4);
	});
	it('arrow keys move focus and the roving tab stop; Home/End jump; focus never leaves the chart', () => {
		const { pts, svg } = chart();
		(pts[0] as unknown as HTMLElement).focus();
		key(pts[0], 'ArrowRight'); key(pts[1], 'ArrowRight');
		expect(document.activeElement).toBe(pts[2]);
		expect(pts[2].getAttribute('tabindex')).toBe('0');
		expect(pts[0].getAttribute('tabindex')).toBe('-1');
		key(pts[2], 'End'); expect(document.activeElement).toBe(pts[4]);
		key(pts[4], 'ArrowRight'); expect(document.activeElement).toBe(pts[4]);      // clamped, not wrapped
		key(pts[4], 'Home'); expect(document.activeElement).toBe(pts[0]);
		expect(svg.contains(document.activeElement)).toBe(true);
	});
	it('a pointer/programmatic focus on a point becomes the roving stop', () => {
		const { pts } = chart();
		(pts[3] as unknown as HTMLElement).focus();
		expect(pts[3].getAttribute('tabindex')).toBe('0');
		expect(pts[0].getAttribute('tabindex')).toBe('-1');
	});
	it('points added later join the roving group (never a second tab stop)', async () => {
		const { svg, pts } = chart(2);
		const extra = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
		extra.setAttribute('tabindex', '0');
		svg.appendChild(extra);
		await Promise.resolve(); await new Promise((r) => setTimeout(r, 0));
		expect([...pts, extra].filter((p) => p.getAttribute('tabindex') === '0')).toHaveLength(1);
	});
});
