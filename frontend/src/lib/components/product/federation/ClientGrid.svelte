<script lang="ts">
	import { CLIENT_LABEL, shortDigest } from '$lib/product/federation/labels';
	import type { ClientState } from '$lib/product/federation/types';
	import type { ClientView } from '$lib/product/federation/live-model';
	import { participationRole } from '$lib/product/federation/participation';
	// ownerBoundClientId is DISPLAY-ONLY (UFL-LITE-002): null/undefined keeps the existing presentation exactly.
	let { live, round = 0, replay = false, ownerBoundClientId = null }: { live: ClientView[]; round?: number; replay?: boolean; ownerBoundClientId?: string | null } = $props();
	const ids = Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`);
	const byId = $derived(Object.fromEntries(live.map((c) => [c.clientId, c])));
	const state = (id: string): ClientState => byId[id]?.state ?? 'IDLE';
	const milestone = (id: string): string => { const m = byId[id]?.milestones[round]; return m === undefined ? 'no milestone yet' : m === 1 ? '100% (completed)' : '0% (started)'; };
</script>
<ul class="grid" data-testid="client-grid" aria-label={ownerBoundClientId ? 'Federated participants' : 'Eight logical clients'}>
	{#each ids as id}
		{@const role = participationRole(id, ownerBoundClientId)}
		<li class={`c s-${state(id).toLowerCase()}${role === 'AUTHENTICATED_OWNER' ? ' owner' : ''}`} data-client={id} data-state={state(id)} data-role={role ?? undefined}>
			{#if role === 'AUTHENTICATED_OWNER'}<span class="mine" data-testid="owner-card-label">★ MY EDGE CLIENT</span>{:else if role === 'SYNTHETIC_PEER'}<span class="peer" data-testid="peer-label">SYNTHETIC PEER</span>{/if}
			<b>{id}</b><span class="st">{replay ? 'REPLAYED EVENT: ' : ''}{CLIENT_LABEL[state(id)]}</span>
			{#if role === 'AUTHENTICATED_OWNER'}<small class="own" data-testid="owner-binding-note">AUTHENTICATED OWNER-BOUND PARTICIPATION · training data: SYNTHETIC ENGINEERING · NOT YOUR PHYSIOLOGY</small>{/if}
			<small>local examples: {byId[id]?.localExamples ?? '--'}</small>
			<small>milestone: {milestone(id)}</small>
			<small>update: <code title={byId[id]?.updateDigests[round] ?? ''}>{shortDigest(byId[id]?.updateDigests[round])}</code></small>
		</li>
	{/each}
</ul>
<style>
	.grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 190px), 1fr)); gap: 8px; } .c { border: 1px solid rgba(148,163,184,.16); padding: 9px 10px; display: grid; gap: 3px; min-width: 0; }
	b { font: 12px 'JetBrains Mono', monospace; } .st { font: 10px 'JetBrains Mono', monospace; letter-spacing: .08em; color: #94a3b8; } small { color: #71829a; font-size: 11px; overflow-wrap: anywhere; }
	.owner { border-color: #2bb8b0; background: rgba(43,184,176,.07); } .mine { font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #2bb8b0; } .peer { font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; } .own { color: #9fe8e3; }
	.s-training { border-color: #fbbf24; } .s-training .st { color: #fbbf24; } .s-update_ready, .s-submitted { border-color: #2bb8b0; } .s-update_ready .st, .s-submitted .st { color: #2bb8b0; } .s-rejected, .s-failed { border-color: #f87171; } .s-rejected .st, .s-failed .st { color: #f87171; }
</style>
