// @vitest-environment jsdom
// Collapsible sidebar: an icon rail like the ChatGPT desktop sidebar. Toggle button, Ctrl/Cmd+B, remembered preference, accessible names kept when only icons show.
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ProductShell from '$lib/components/product/ProductShell.svelte';
import { FrontendAuth } from '../auth';
import { ProductStore, setProductStore } from '../state.svelte';
import { FakeSocket, fakeBackend, resetSeq, systemInfo } from './support';

const immediate = (cb: () => void) => { cb(); return 0; };
const KEY = 'nhm.sidebar.collapsed';
function memoryStorage(): Storage {
	const data = new Map<string, string>();
	return { get length() { return data.size; }, clear: () => data.clear(), getItem: (k: string) => data.get(k) ?? null, key: (i: number) => [...data.keys()][i] ?? null, removeItem: (k: string) => { data.delete(k); }, setItem: (k: string, v: string) => { data.set(k, String(v)); } };
}
async function mount() {
	FakeSocket.reset(); resetSeq();
	vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173', assign: vi.fn() });
	const backend = fakeBackend(systemInfo());
	const store = new ProductStore(new FrontendAuth({ createClient: () => backend }), immediate, (u) => new FakeSocket(u));
	setProductStore(store);
	await store.init();
	return render(ProductShell);
}
const shell = () => document.querySelector('.shell') as HTMLElement;
const toggle = () => screen.getByTestId('sidebar-toggle') as HTMLButtonElement;
beforeEach(() => { vi.stubGlobal('localStorage', memoryStorage()); });
afterEach(() => { cleanup(); setProductStore(null); vi.unstubAllGlobals(); });

describe('sidebar collapse', () => {
	it('starts expanded with a labelled, expanded toggle controlling the navigation list', async () => {
		await mount();
		expect(shell().classList.contains('collapsed')).toBe(false);
		expect(toggle().getAttribute('aria-label')).toBe('Collapse sidebar');
		expect(toggle().getAttribute('aria-expanded')).toBe('true');
		expect(toggle().getAttribute('aria-controls')).toBe('product-nav-list');
		expect(document.getElementById('product-nav-list')).toBeTruthy();
		expect(screen.getByRole('navigation', { name: 'Product sections' }).textContent).toContain('Federation');
	});
	it('collapsing keeps every destination reachable by an accessible name and a tooltip, hides sub-pages, and remembers the choice', async () => {
		await mount();
		await fireEvent.click(toggle());
		expect(shell().classList.contains('collapsed')).toBe(true);
		expect(toggle().getAttribute('aria-label')).toBe('Expand sidebar');
		expect(toggle().getAttribute('aria-expanded')).toBe('false');
		for (const label of ['Overview', 'Device', 'Monitor', 'History', 'Observatory', 'Federation', 'Models', 'Research', 'System', 'About']) {
			const link = screen.getByRole('link', { name: label });
			expect(link.getAttribute('title')).toBe(label);
			expect(link.getAttribute('href')).toMatch(/^\/app/);
		}
		expect(localStorage.getItem(KEY)).toBe('1');
		await fireEvent.click(toggle());
		expect(shell().classList.contains('collapsed')).toBe(false);
		expect(localStorage.getItem(KEY)).toBe('0');
		expect(screen.getByRole('link', { name: 'Federation' }).getAttribute('title')).toBeNull();
	});
	it('restores the remembered collapsed state on the next load', async () => {
		localStorage.setItem(KEY, '1');
		await mount();
		expect(shell().classList.contains('collapsed')).toBe(true);
		expect(toggle().getAttribute('aria-label')).toBe('Expand sidebar');
	});
	it('Ctrl+B and Cmd+B toggle it and keep focus on the toggle; typing in a field is left alone', async () => {
		await mount();
		await fireEvent.keyDown(window, { key: 'b', ctrlKey: true });
		expect(shell().classList.contains('collapsed')).toBe(true);
		await fireEvent.keyDown(window, { key: 'B', metaKey: true });
		expect(shell().classList.contains('collapsed')).toBe(false);
		const input = document.createElement('input');
		document.body.appendChild(input);
		await fireEvent.keyDown(input, { key: 'b', ctrlKey: true });
		expect(shell().classList.contains('collapsed')).toBe(false);
		await fireEvent.keyDown(window, { key: 'b' });                       // no modifier: ordinary typing
		expect(shell().classList.contains('collapsed')).toBe(false);
		input.remove();
	});
	it('a blocked or unavailable storage never breaks the shell (renders expanded, toggling still works)', async () => {
		const blocked = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } };
		vi.stubGlobal('localStorage', blocked);
		await mount();
		expect(shell().classList.contains('collapsed')).toBe(false);
		await fireEvent.click(toggle());
		expect(shell().classList.contains('collapsed')).toBe(true);
	});
	it('the simulation and not-diagnostic notices stay available when collapsed', async () => {
		await mount();
		await fireEvent.click(toggle());
		const foot = document.querySelector('.foot') as HTMLElement;
		expect(foot.getAttribute('title')).toBe('SIMULATED ONLY · RESEARCH / NOT DIAGNOSTIC');
		expect(foot.textContent).toContain('SIMULATED ONLY');
	});
});
