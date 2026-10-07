<script lang="ts">
	// Current-round counters: ONLY reported values (milestones, update digests, accepted count). Segments = clients, never a percentage.
	import { roundCounts, currentRoundView } from '$lib/product/federation/presentation';
	import type { FederationView } from '$lib/product/federation/live-model';
	let { view, plannedRounds = 0 }: { view: FederationView; plannedRounds?: number } = $props();
	const roundId = $derived(currentRoundView(view)?.roundId ?? view.currentRound);
	const c = $derived(roundCounts(view, roundId));
	const rows = $derived([
		{ id: 'train', label: 'Local training complete', n: c.trainingComplete },
		{ id: 'ready', label: 'Updates ready', n: c.updatesReady },
		{ id: 'acc', label: 'Updates accepted', n: c.accepted }
	]);
</script>
<div class="rp" data-testid="round-progress">
	<h4>{roundId ? `ROUND ${roundId} OF ${plannedRounds || '--'}` : 'WAITING FOR ROUND 1'}</h4>
	{#each rows as r (r.id)}
		<div class="row"><span class="lab">{r.label}</span><span class="seg" aria-hidden="true">{#each Array.from({ length: c.total }, (_, i) => i) as i}<i class:on={i < r.n}></i>{/each}</span><b data-testid={`rp-${r.id}`}>{r.n} / {c.total}</b></div>
	{/each}
	{#if c.state}<p class="st">Round state reported by the backend: <code>{c.state}</code></p>{/if}
</div>
<style>
	.rp { display: grid; gap: 8px; } h4 { margin: 0; font: 500 15px 'Space Grotesk', sans-serif; color: #e5f1f0; letter-spacing: .02em; } .row { display: grid; grid-template-columns: minmax(0, 9.5em) 1fr auto; gap: 8px; align-items: center; font-size: 12px; color: #cbd5e1; } b { font: 12px 'JetBrains Mono', monospace; }
	.seg { display: flex; gap: 3px; } .seg i { flex: 1; height: 8px; min-width: 6px; background: rgba(148,163,184,.18); } .seg i.on { background: #a78bfa; } .st { margin: 0; font-size: 11px; color: #71829a; } code { font: 11px 'JetBrains Mono', monospace; }
	@media (max-width: 480px) { .row { grid-template-columns: 1fr auto; } .seg { grid-column: 1 / -1; order: 3; } }
</style>
