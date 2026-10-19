// @vitest-environment jsdom
// The guided demonstration page as a presenter's tool: every step is rendered with its four parts, presenter mode steps through them with the keyboard and a timer, ticks persist,
// and the page keeps the hooks the real-browser gate relies on.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Page from '../../../routes/app/demo/+page.svelte';
import { DEMO_STEPS } from '../demo-path';

beforeEach(() => {
	const store = new Map<string, string>();       // the test environment has no Web Storage: a small stand-in, as a browser would provide
	vi.stubGlobal('localStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); }, clear: () => store.clear() });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('guided demo page', () => {
	it('renders every step as a card with do / understand / say / if it fails, an evidence mode and a link that resolves', () => {
		render(Page);
		const items = screen.getByTestId('demo-steps').querySelectorAll('li[data-step]');
		expect([...items].map((li) => li.getAttribute('data-step'))).toEqual(DEMO_STEPS.map((s) => s.id));
		for (const [i, li] of [...items].entries()) {
			expect(li.querySelector('[data-testid="demo-mode"]')?.textContent?.length).toBeGreaterThan(3);
			expect(li.querySelector('a.go')?.getAttribute('href')).toBe(DEMO_STEPS[i].href);
			const text = li.textContent ?? '';
			for (const part of ['Do', 'Understand', 'Say', 'If it fails']) expect(text).toContain(part);
		}
		expect(screen.getByTestId('demo-modes').querySelectorAll('p').length).toBe(6);
		expect(screen.getByTestId('story-map').querySelectorAll('button').length).toBe(DEMO_STEPS.length);
		expect(screen.getByRole('heading', { level: 1 }).textContent).toContain('One story');
	});
	it('presenter mode shows a bar, steps with the arrow keys, ticks the step it leaves and says how far ahead or behind the plan it is', async () => {
		vi.useFakeTimers();
		render(Page);
		expect(screen.queryByTestId('presenter-bar')).toBeNull();
		await fireEvent.click(screen.getByTestId('start-presenting'));
		expect(screen.getByTestId('presenter-bar').textContent).toContain(`1/${DEMO_STEPS.length}`);
		await vi.advanceTimersByTimeAsync(5000);
		expect(screen.getByTestId('presenter-elapsed').textContent).toBe('0:05');
		expect(screen.getByTestId('presenter-drift').textContent).toBe('on pace');
		await fireEvent.keyDown(window, { key: 'ArrowRight' });
		expect(screen.getByTestId('presenter-bar').textContent).toContain(`2/${DEMO_STEPS.length}`);
		expect(screen.getByTestId('covered-count').textContent).toContain(`1/${DEMO_STEPS.length}`);
		expect(screen.getByTestId(`covered-${DEMO_STEPS[0].id}`).getAttribute('aria-pressed')).toBe('true');
		await vi.advanceTimersByTimeAsync(120000);
		expect(screen.getByTestId('presenter-drift').textContent).toMatch(/behind/);                        // 2 minutes in, but step 2 planned to start at 0:30
		await fireEvent.keyDown(window, { key: ' ' });                                                   // space pauses the timer
		const frozen = screen.getByTestId('presenter-elapsed').textContent;
		await vi.advanceTimersByTimeAsync(10000);
		expect(screen.getByTestId('presenter-elapsed').textContent).toBe(frozen);
		await fireEvent.keyDown(window, { key: 'ArrowLeft' });
		expect(screen.getByTestId('presenter-bar').textContent).toContain(`1/${DEMO_STEPS.length}`);
		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(screen.queryByTestId('presenter-bar')).toBeNull();
	});
	it('ignores presenter keys outside presenter mode and keeps covered ticks across a reload', async () => {
		const first = render(Page);
		await fireEvent.keyDown(window, { key: 'ArrowRight' });
		expect(screen.getByTestId('covered-count').textContent).toContain(`0/${DEMO_STEPS.length}`);
		await fireEvent.click(screen.getByTestId(`covered-${DEMO_STEPS[2].id}`));
		first.unmount();
		render(Page);
		await waitFor(() => expect(screen.getByTestId(`covered-${DEMO_STEPS[2].id}`).getAttribute('aria-pressed')).toBe('true'));
		expect(screen.getByTestId('covered-count').textContent).toContain(`1/${DEMO_STEPS.length}`);
	});
	it('states the boundaries before anything else and offers the pre-flight commands with copy buttons', () => {
		render(Page);
		const text = document.body.textContent ?? '';
		expect(text).toMatch(/not clinical or diagnostic/i);
		expect(text).toContain('scripts.demo_preflight');
		expect(text).toContain('--durable');
		expect(screen.getAllByRole('button', { name: /^Copy:/ }).length).toBe(3);
	});
});
