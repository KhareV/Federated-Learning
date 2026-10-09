<script lang="ts">
	// RUN STATUS strip: counts and states come ONLY from the validated federation events (accepted = coordinator acceptances) and the evaluation records; nothing is predicted.
	import type { FederationView } from '$lib/product/federation/live-model';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio, view }: { studio: StudioStore; view: FederationView } = $props();
	const planned = $derived(studio.plannedRounds || view.plannedRounds);
	const clients = $derived(view.clientCount || 8);
	const accepted = $derived(view.submittedCount);
	const status = $derived(studio.run?.status ?? view.runStatus ?? '--');
	const roundState = (r: number) => view.rounds.find((x) => x.roundId === r);
	const dot = (r: number): 'done' | 'active' | 'pending' => {
		const st = roundState(r);
		if (st && (st.state === 'COMPLETED' || st.stateDigest !== null)) return 'done';
		return r === view.currentRound && status === 'RUNNING' ? 'active' : 'pending';
	};
	const PHASE: Record<string, string> = { CREATED: 'CREATED', BUILDING_COHORT: 'PREPARING 8 SYNTHETIC CLIENT DATASETS', MONITORING_SITE_00: 'MONITORING THE SIMULATED SITE_00 SOURCE', EVALUATING: 'EVALUATING COMMITTED CHECKPOINTS', EXPORTING: 'EXPORT PREPARING', DONE: 'COMPLETE', FAILED: 'FAILED' };
	const ROUND_STAGE: Record<string, string> = { CREATED: 'ROUND CREATED', COLLECTING: 'COLLECTING CLIENT DATA', LOCAL_TRAINING: 'LOCAL TRAINING', UPDATES_READY: 'UPDATES READY', AGGREGATING: 'AGGREGATION', CANDIDATE_CREATED: 'CANDIDATE CREATED', VALIDATING: 'CANDIDATE VALIDATION', ACCEPTED_TO_SANDBOX: 'ACCEPTED TO SANDBOX', COMPLETED: 'ROUND COMMITTED', REJECTED: 'REJECTED', FAILED: 'FAILED' };
	const stage = $derived.by(() => {
		const phase = studio.run?.phase;
		const st = roundState(view.currentRound);
		if (status === 'RUNNING' && (!st || view.currentRound === 0) && phase && PHASE[phase]) return PHASE[phase];
		if (status === 'RUNNING' && st) return ROUND_STAGE[st.state] ?? st.state;
		if (status === 'COMPLETED' && phase && phase !== 'DONE' && PHASE[phase]) return PHASE[phase];
		return status === 'COMPLETED' ? 'COMPLETE' : status === 'FAILED' ? 'FAILED' : (phase && PHASE[phase]) || status;
	});
	const evalGlyph = (r: number) => ({ COMPLETED: 'E✓', EVALUATING: 'E…', QUEUED: 'Eq', FAILED: 'E✗', NOT_SUBMITTED: '' })[studio.statusOf(r)];
	const selectable = (r: number) => r === 0 || dot(r) !== 'pending' || r <= studio.latestCommittedRound;
</script>
<section class="strip" aria-label="Run status" data-testid="run-status-strip">
	<p class="head" role="status" aria-live="polite" data-testid="run-status-line"><b class={status.toLowerCase()}>{status}</b> · ROUND {Math.min(view.currentRound, planned)}/{planned} · <span data-testid="accepted-counter">{accepted}/{clients * planned}</span> ACCEPTED UPDATES</p>
	<ol class="dots" aria-label="Communication rounds">
		<li><button type="button" class="r0" class:sel={studio.selectedRound === 0} aria-label="Round 0, initial global state" aria-pressed={studio.selectedRound === 0} onclick={() => studio.selectRound(0)}>R0<small>{evalGlyph(0)}</small></button></li>
		{#each Array.from({ length: planned }, (_, i) => i + 1) as r (r)}
			<li><button type="button" class={dot(r)} class:sel={studio.selectedRound === r} disabled={!selectable(r)} aria-label={`Round ${r}: ${dot(r) === 'done' ? 'committed' : dot(r) === 'active' ? 'in progress' : 'not started'}${evalGlyph(r) ? ', evaluation ' + studio.statusOf(r).toLowerCase() : ''}`} aria-pressed={studio.selectedRound === r} data-testid={`dot-R${r}`} onclick={() => studio.selectRound(r)}>
				<i aria-hidden="true">{dot(r) === 'done' ? '●' : dot(r) === 'active' ? '◉' : '○'}</i>R{r}<small>{evalGlyph(r)}</small></button></li>
		{/each}
	</ol>
	<p class="stage" data-testid="current-stage">Current stage: <b>{stage}</b>{#if studio.run?.failure} · <span class="err" role="alert">FAILED — not a candidate: {studio.run.failure.code}: {studio.run.failure.message}.{#if studio.run.engine === 'FL10_10R'} Restart from R0.{/if}</span>{/if}</p>
	<p class="legend">● committed · ◉ executing · ○ not started · E✓ evaluated · E… evaluating · Eq evaluation queued (a queued round has no metrics yet)</p>
</section>
<style>
	.strip { border: 1px solid rgba(167,139,250,.4); background: rgba(167,139,250,.05); padding: 12px 14px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; min-width: 0; } .head { margin: 0; font: 13px 'JetBrains Mono', monospace; letter-spacing: .06em; color: #e5e7eb; } .head b { color: #c4b5fd; } .head b.running { color: #fbbf24; } .head b.completed { color: #86efac; } .head b.failed { color: #f87171; }
	.dots { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; } button { background: #0a0f1f; color: #cbd5e1; border: 1px solid rgba(148,163,184,.35); min-height: 36px; min-width: 52px; padding: 4px 8px; font: 11px 'JetBrains Mono', monospace; cursor: pointer; display: inline-flex; flex-direction: column; align-items: center; line-height: 1.15; }
	button i { font-style: normal; font-size: 13px; } button small { color: #71829a; font-size: 9px; min-height: 10px; } button.done { border-color: rgba(167,139,250,.7); color: #e9e3ff; } button.active { border-color: #fbbf24; color: #fde68a; animation: pulse 1.4s ease-in-out infinite; } button.sel { outline: 2px solid #2bb8b0; outline-offset: 1px; } button:disabled { opacity: .4; cursor: not-allowed; } button:focus-visible { outline: 2px solid #2bb8b0; outline-offset: 2px; }
	.stage, .legend { margin: 0; font-size: 12px; color: #94a3b8; } .stage b { color: #e5e7eb; font: 12px 'JetBrains Mono', monospace; letter-spacing: .05em; } .legend { font-size: 11px; color: #71829a; } .err { color: #f87171; }
	@keyframes pulse { 50% { opacity: .6; } } @media (prefers-reduced-motion: reduce) { button.active { animation: none; } }
	p, li, small, button { overflow-wrap: anywhere; }
</style>
