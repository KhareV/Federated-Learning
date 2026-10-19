// @vitest-environment jsdom
// The site cursor follows the mouse instantly, like the system pointer: no spring smoothing.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { cleanup, render } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import SmoothCursor from '../smooth-cursor.svelte';

const moveTo = (x: number, y: number) => window.dispatchEvent(new MouseEvent('mousemove', { clientX: x, clientY: y }));

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
	it('stays hidden until the mouse first moves, and keeps no spring, rotation or scale animation', () => {
		const { getByTestId } = render(SmoothCursor);
		expect(getByTestId('site-cursor').style.opacity).toBe('0');
		const source = readFileSync(join(__dirname, '../smooth-cursor.svelte'), 'utf8');
		expect(source).not.toMatch(/useSpring|motion-sv|requestAnimationFrame|rotate|scale\.set/);
	});
});
