// @vitest-environment jsdom
// The site cursor follows the mouse instantly, like the system pointer (no spring smoothing), and its head turns toward the direction of travel.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { cleanup, render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import SmoothCursor from '../smooth-cursor.svelte';

const moveTo = (x: number, y: number) => window.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y }));
const angleOf = (el: HTMLElement) => Number(/rotate\((-?[\d.]+)deg\)/.exec(el.style.transform)?.[1]);

import { afterEach } from 'vitest';
afterEach(cleanup);

describe('site cursor', () => {
	it('is at the mouse position immediately after each move, with no easing in between', () => {
		const { getByTestId } = render(SmoothCursor);
		const el = getByTestId('site-cursor');
		moveTo(400, 300);
		expect(el.style.transform).toBe('translate3d(375px, 284.25px, 0)');        // the arrow's tip (25, 15.75 from its corner) sits on the pointer
		moveTo(10, 20);                                                           // a large jump is also applied at once, not approached over frames
		expect(el.style.transform).toBe('translate3d(-15px, 4.25px, 0)');
		moveTo(900, 700);
		expect(el.style.transform).toBe('translate3d(875px, 684.25px, 0)');
	});
	it('stays hidden until the mouse first moves, and keeps no spring, frame throttle or scale animation', () => {
		const { getByTestId } = render(SmoothCursor);
		expect(getByTestId('site-cursor').style.opacity).toBe('0');
		const source = readFileSync(join(__dirname, '../smooth-cursor.svelte'), 'utf8');
		expect(source).not.toMatch(/useSpring|motion-sv|requestAnimationFrame|scale\.set/);
	});
	it('turns the arrow head toward the direction the mouse moves, about the tip, without delaying the position', () => {
		const { getByTestId } = render(SmoothCursor);
		const el = getByTestId('site-cursor');
		const head = getByTestId('site-cursor-head');
		expect(head.style.transformOrigin).toBe('25px 15.75px');                    // rotation is about the tip, so the tip stays on the pointer
		moveTo(100, 100);
		moveTo(200, 100);                                                         // moving right: the arrow (drawn pointing up) turns 90 degrees clockwise
		expect(angleOf(head)).toBeCloseTo(90);
		expect(el.style.transform).toBe('translate3d(175px, 84.25px, 0)');
		moveTo(200, 200);                                                         // moving down
		expect(angleOf(head)).toBeCloseTo(180);
		moveTo(100, 200);                                                         // moving left
		expect(angleOf(head)).toBeCloseTo(270);
		moveTo(100, 100);                                                         // moving up returns to 360 (the short way round, never a reverse spin)
		expect(angleOf(head)).toBeCloseTo(360);
	});
	it('ignores sub-threshold tremor so the head does not jitter', () => {
		const { getByTestId } = render(SmoothCursor);
		const head = getByTestId('site-cursor-head');
		moveTo(100, 100);
		moveTo(300, 100);
		const settled = head.style.transform;
		moveTo(300, 102);
		moveTo(301, 102);
		expect(head.style.transform).toBe(settled);
	});
});
