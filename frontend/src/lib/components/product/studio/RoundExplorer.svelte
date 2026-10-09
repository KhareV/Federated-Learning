<script lang="ts">
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio, canFollow = true }: { studio: StudioStore; canFollow?: boolean } = $props();
	const GLYPH: Record<string, string> = { COMPLETED: 'evaluated', EVALUATING: 'evaluating', QUEUED: 'queued', FAILED: 'failed', NOT_SUBMITTED: 'not committed' };
	const enabled = (r: number) => r === 0 || r <= Math.max(studio.latestCommittedRound, studio.executingRound) || studio.run?.status === 'COMPLETED' || studio.statusOf(r) !== 'NOT_SUBMITTED';
</script>
<div class="ex" data-testid="round-explorer">
	<div class="bar" role="group" aria-label="Select a round to inspect">
		{#each studio.rounds as r (r)}
			<button type="button" class:sel={studio.selectedRound === r} class:live={studio.followLive && studio.selectedRound === r} disabled={!enabled(r)} aria-pressed={studio.selectedRound === r} data-testid={`round-btn-R${r}`} title={`R${r}: ${GLYPH[studio.statusOf(r)]}`} onclick={() => studio.selectRound(r)}>R{r}<small class={studio.statusOf(r).toLowerCase()}>{GLYPH[studio.statusOf(r)]}</small></button>
		{/each}
		{#if canFollow}<button type="button" class="ret" disabled={studio.followLive} onclick={() => studio.returnToLive()} data-testid="return-to-live">RETURN TO LIVE</button>{/if}
	</div>
	<p class="dim" data-testid="follow-state">{studio.followLive ? 'FOLLOWING LIVE: panels track the actual current round.' : `INSPECTING ROUND ${studio.selectedRound}: new events keep arriving but do not move your selection.`} Evaluation of a round starts only after its state is committed.</p>
</div>
<style>
	.ex { display: grid; gap: 8px; } .bar { display: flex; flex-wrap: wrap; gap: 6px; } button { background: #0a0f1f; color: #e2e8f0; border: 1px solid rgba(148,163,184,.35); min-height: 40px; min-width: 56px; padding: 4px 10px; font: 12px 'JetBrains Mono', monospace; cursor: pointer; display: inline-flex; flex-direction: column; align-items: center; line-height: 1.2; }
	button small { font-size: 9px; color: #71829a; } small.completed { color: #86efac; } small.evaluating { color: #fbbf24; } small.queued { color: #94a3b8; } small.failed { color: #f87171; } button.sel { border-color: #2bb8b0; color: #9fe8e3; box-shadow: inset 0 0 0 1px #2bb8b0; } button.live { border-color: #fbbf24; }
	button:disabled { opacity: .4; cursor: not-allowed; } button:focus-visible { outline: 2px solid #2bb8b0; outline-offset: 2px; } .ret { margin-left: auto; border-color: rgba(167,139,250,.7); color: #e9e3ff; } .dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5; }
</style>
