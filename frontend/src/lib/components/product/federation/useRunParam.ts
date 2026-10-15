// URL-addressable run selection (?run=<id>): refresh reloads from the backend; nothing is kept in localStorage.
import { goto } from '$app/navigation';
import type { FederationStore } from '$lib/product/federation/state.svelte';

export async function bootRun(fed: FederationStore, runParam: string | null, pathname?: string): Promise<void> {
	await fed.loadRuns();
	// SELECTED-RUN PERSISTENCE: opening a run-scoped page without ?run= re-attaches to the run already selected in this session (and puts it in the URL),
	// instead of showing an empty page next to a run the user was just looking at.
	const target = runParam ?? fed.run?.run_id ?? null;
	if (!target) return;
	await fed.selectRun(target);
	if (!runParam && pathname) await goto(`${pathname}?run=${encodeURIComponent(target)}`, { replaceState: true, noScroll: true, keepFocus: true });
}
export async function chooseRun(fed: FederationStore, pathname: string, id: string): Promise<void> {
	await goto(`${pathname}?run=${encodeURIComponent(id)}`, { replaceState: true, noScroll: true, keepFocus: true });
	await fed.selectRun(id);
}
