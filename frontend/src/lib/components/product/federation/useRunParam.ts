// URL-addressable run selection (?run=<id>): refresh reloads from the backend; nothing is kept in localStorage.
import { goto } from '$app/navigation';
import type { FederationStore } from '$lib/product/federation/state.svelte';

export async function bootRun(fed: FederationStore, runParam: string | null): Promise<void> {
	await fed.loadRuns();
	if (runParam) await fed.selectRun(runParam);
}
export async function chooseRun(fed: FederationStore, pathname: string, id: string): Promise<void> {
	await goto(`${pathname}?run=${encodeURIComponent(id)}`, { replaceState: true, noScroll: true, keepFocus: true });
	await fed.selectRun(id);
}
