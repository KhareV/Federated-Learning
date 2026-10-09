<script lang="ts">
	// The key interactive graphs under the selected-round metrics: real measured series only; the selected round is marked, pending rounds are marked pending.
	import Fl10Chart from '$lib/components/product/observatory/Fl10Chart.svelte';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	import type { Fl10Spec } from '$lib/product/observatory/fl10';
	let { studio }: { studio: StudioStore } = $props();
	$effect(() => { if (studio.run?.evaluation.available) void studio.ensureFigures(); });
	const spec = (id: string) => studio.figures?.specs[id] as unknown as Fl10Spec | undefined;
	const pick = (x: number) => studio.selectRound(x);
</script>
<div class="g" data-testid="key-graphs">
	{#if !studio.run?.evaluation.available}
		<p class="dim" data-testid="no-graphs">No per-round measurements exist for this run, so there is nothing to plot (no placeholder series is drawn).</p>
	{:else if !studio.figures}
		<p class="dim" role="status" data-testid="graphs-loading">Loading measured series…</p>
	{:else}
		{#each ['FL10_FIG04', 'FL10_FIG05', 'FL10_FIG06', 'FL10_FIG02'] as id (id)}
			{@const s = spec(id)}
			{#if s}<div class="one" data-availability={studio.figures.specs[id].availability}>
				<Fl10Chart spec={s} initialView={id === 'FL10_FIG05' ? 'all' : null} selectedX={id === 'FL10_FIG02' ? (studio.selectedRound >= 1 ? studio.selectedRound : null) : studio.selectedRound} onPickX={pick} />
				{#if studio.figures.specs[id].availability !== 'AVAILABLE'}<p class="avail" data-testid={`avail-${id}`}>{studio.figures.specs[id].availability}: {studio.figures.specs[id].availability_detail}</p>{/if}</div>{/if}
		{/each}
	{/if}
</div>
<style>
	.g { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 10px; min-width: 0; } .one { min-width: 0; display: grid; gap: 4px; } .dim { margin: 0; color: #94a3b8; font-size: 13px; } .avail { margin: 0; font: 11px 'JetBrains Mono', monospace; color: #fbbf24; }
</style>
