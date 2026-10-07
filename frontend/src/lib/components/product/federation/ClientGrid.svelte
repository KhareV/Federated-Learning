<script lang="ts">
	import { CLIENT_LABEL } from '$lib/product/federation/labels';
	import type { ClientState } from '$lib/product/federation/types';
	import type { ClientView } from '$lib/product/federation/live-model';
	import { participationRole } from '$lib/product/federation/participation';
	import { nodeState, NODE_LABEL, NODE_MARK } from '$lib/product/federation/presentation';
	// ownerBoundClientId is DISPLAY-ONLY (UFL-LITE-002): null/undefined keeps the existing presentation exactly.
	// UI-ENH-001: the same eight cards are laid out as a client network around the coordinator on wide screens and as a plain grid on narrow ones (one DOM, CSS-only switch).
	let { live, round = 0, replay = false, ownerBoundClientId = null, selected = null, onSelect = undefined, runDone = false }: { live: ClientView[]; round?: number; replay?: boolean; ownerBoundClientId?: string | null; selected?: string | null; onSelect?: (id: string) => void; runDone?: boolean } = $props();
	const ids = Array.from({ length: 8 }, (_, i) => `SIM_FL_SITE_0${i}`);
	const byId = $derived(Object.fromEntries(live.map((c) => [c.clientId, c])));
	const state = (id: string): ClientState => byId[id]?.state ?? 'IDLE';
	const milestone = (id: string): string => { const m = byId[id]?.milestones[round]; return m === undefined ? 'no milestone yet' : m === 1 ? '100% (completed)' : '0% (started)'; };
	const pos = (i: number) => { const a = (-90 + i * 45) * (Math.PI / 180); return { x: 50 + 37 * Math.cos(a), y: 50 + 33 * Math.sin(a) }; };
	const produced = (id: string): boolean => byId[id]?.updateDigests[round] !== undefined;
</script>
<div class="net" data-testid="client-network">
	<svg class="lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{#each ids as id, i}{@const p = pos(i)}<line x1="50" y1="50" x2={p.x} y2={p.y} class={nodeState(byId[id], round, runDone) === 'TRAINING' ? 'act' : ''} />{/each}</svg>
	<div class="hub" data-testid="coordinator"><span class="k">COORDINATOR</span><b>Combines model updates</b><small>receives updates, never local examples</small></div>
	<ul class="grid" data-testid="client-grid" aria-label={ownerBoundClientId ? 'Federated participants' : 'Eight logical clients'}>
		{#each ids as id, i}
			{@const role = participationRole(id, ownerBoundClientId)}
			{@const ns = nodeState(byId[id], round, runDone)}
			{@const p = pos(i)}
			<li class={`c s-${state(id).toLowerCase()} n-${ns.toLowerCase()}${role === 'AUTHENTICATED_OWNER' ? ' owner' : ''}${selected === id ? ' sel' : ''}`} style={`left: ${p.x}%; top: ${p.y}%`} data-client={id} data-state={state(id)} data-role={role ?? undefined}>
				<button type="button" class="node" aria-pressed={selected === id} aria-label={`Show details for ${id}`} onclick={() => onSelect?.(id)}>
					{#if role === 'AUTHENTICATED_OWNER'}<span class="mine" data-testid="owner-card-label">★ MY EDGE CLIENT</span>{:else if role === 'SYNTHETIC_PEER'}<span class="peer" data-testid="peer-label">SYNTHETIC PEER</span>{/if}
					<b>{id}</b><span class="st"><span aria-hidden="true">{NODE_MARK[ns]}</span> {replay ? 'REPLAYED EVENT: ' : ''}{NODE_LABEL[ns]}<span class="raw"> ({CLIENT_LABEL[state(id)]})</span></span>
					{#if role === 'AUTHENTICATED_OWNER'}<small class="own" data-testid="owner-binding-note">TRAINING DATA: SYNTHETIC ENGINEERING FIXTURE · NOT YOUR PHYSIOLOGY</small>{/if}
					<small>local examples: {byId[id]?.localExamples ?? '--'}</small>
					<small>milestone: {milestone(id)}</small>
					<small>update: {#if produced(id)}<code title={byId[id]?.updateDigests[round] ?? ''}>{(byId[id]?.updateDigests[round] ?? '').slice(0, 10)}…</code> produced{:else}not yet produced{/if}</small>
				</button>
			</li>
		{/each}
	</ul>
</div>
<style>
	.net { position: relative; min-height: 660px; min-width: 0; } .lines { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; } .lines line { stroke: rgba(148,163,184,.28); stroke-width: .35; vector-effect: non-scaling-stroke; stroke-width: 1px; } .lines line.act { stroke: #a78bfa; }
	.hub { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); display: grid; gap: 3px; justify-items: center; text-align: center; padding: 12px 14px; border: 1px solid rgba(167,139,250,.6); background: #0a0f1f; max-width: 190px; z-index: 1; } .hub .k { font: 9.5px 'JetBrains Mono', monospace; letter-spacing: .14em; color: #c4b5fd; } .hub b { font: 500 13px 'Space Grotesk', sans-serif; color: #e5f1f0; } .hub small { font-size: 10.5px; color: #94a3b8; line-height: 1.4; }
	.grid { list-style: none; margin: 0; padding: 0; position: absolute; inset: 0; } .c { position: absolute; transform: translate(-50%, -50%); width: 168px; min-width: 0; z-index: 2; }
	.node { width: 100%; text-align: left; font: inherit; color: inherit; cursor: pointer; border: 1px solid rgba(148,163,184,.25); background: #0a0f1f; padding: 8px 10px; display: grid; gap: 2px; min-height: 24px; box-sizing: border-box; } .node:hover { border-color: rgba(148,163,184,.55); } .node:focus-visible { outline: 2px solid #2bb8b0; outline-offset: 2px; }
	b { font: 12px 'JetBrains Mono', monospace; } .st { font: 10px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #94a3b8; } .raw { color: #71829a; letter-spacing: 0; } small { color: #71829a; font-size: 10.5px; overflow-wrap: anywhere; line-height: 1.35; }
	.owner .node { border-color: #2bb8b0; background: #08201f; } .mine { font: 10.5px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #2bb8b0; } .peer { font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; } .own { color: #9fe8e3; }
	.sel .node { box-shadow: 0 0 0 2px rgba(167,139,250,.65); } .n-training .node { border-color: #a78bfa; } .n-training .st { color: #c4b5fd; } .n-training_complete .node, .n-update_ready .node { border-color: #818cf8; } .n-accepted .node, .n-complete .node { border-color: #2bb8b0; } .n-accepted .st, .n-complete .st { color: #2bb8b0; } .n-failed .node { border-color: #f87171; } .n-failed .st { color: #f87171; }
	@media (max-width: 1100px) {
		.net { min-height: 0; display: grid; gap: 10px; } .lines { display: none; } .hub { position: static; transform: none; max-width: none; justify-items: start; text-align: left; } .grid { position: static; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 190px), 1fr)); gap: 8px; } .c { position: static; transform: none; width: auto; }
	}
</style>
