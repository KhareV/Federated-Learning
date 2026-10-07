<script lang="ts">
	// Stage progression for the CURRENT round, derived ONLY from the reported run/round state (presentation.stageProgress). No fake progress, no percentages.
	import { stageProgress } from '$lib/product/federation/presentation';
	import type { FederationView } from '$lib/product/federation/live-model';
	let { view, replay = false }: { view: FederationView; replay?: boolean } = $props();
	const stages = $derived(stageProgress(view));
	const mark = { done: '✓', active: '●', pending: '○', failed: '✕' } as const;
	const word = { done: 'done', active: 'in progress', pending: 'not started', failed: 'failed' } as const;
</script>
<div class="wrap" data-testid="process-stepper">
	<ol class="steps" aria-label="Federation stages for the current round">
		{#each stages as s (s.id)}
			<li class={`st st-${s.status}`} aria-current={s.status === 'active' ? 'step' : undefined} data-stage={s.id} data-status={s.status}><span class="m" aria-hidden="true">{mark[s.status]}</span><span class="l">{s.label}</span><span class="sr">{word[s.status]}</span></li>
		{/each}
	</ol>
	{#if replay}<p class="rp" data-testid="stepper-replay">REPLAYING HISTORICAL EVENTS · NO TRAINING EXECUTING</p>{/if}
</div>
<style>
	.wrap { display: grid; gap: 8px; } .steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }
	.st { position: relative; border: 1px solid rgba(148,163,184,.2); padding: 8px 8px 9px; display: grid; gap: 4px; align-content: start; min-width: 0; color: #71829a; } .m { font: 14px 'JetBrains Mono', monospace; } .l { font-size: 11.5px; line-height: 1.35; overflow-wrap: anywhere; }
	.st-done { border-color: rgba(43,184,176,.5); color: #2bb8b0; background: rgba(43,184,176,.05); } .st-active { border-color: #a78bfa; color: #e9e3ff; background: rgba(167,139,250,.12); box-shadow: 0 0 0 1px rgba(167,139,250,.4) inset; } .st-failed { border-color: #f87171; color: #f87171; }
	.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
	@media (prefers-reduced-motion: no-preference) { .st-active .m { animation: pulse 1.6s ease-in-out infinite; } @keyframes pulse { 50% { opacity: .45; } } }
	.rp { margin: 0; border: 1px solid rgba(148,163,184,.5); color: #cbd5e1; padding: 6px 10px; font: 11px 'JetBrains Mono', monospace; letter-spacing: .08em; }
	@media (max-width: 820px) { .steps { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
