<script lang="ts">
	import { crossesCohorts, runCohortName, trainedOn } from '$lib/product/studio/candidate-text';
	// First-screen summary of the SELECTED run: what it is, how far it got, the latest MEASURED key result (labelled with its round) and where to go next.
	// Every value comes from the validated run context and the stored evaluation records of this run; nothing is computed or defaulted here.
	import { display } from '$lib/product/studio/metrics';
	import type { RunContext } from '$lib/product/federation/run-context';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { ctx, studio, status, algorithm, currentRound, plannedRounds, accepted, expected }: {
		ctx: RunContext; studio: StudioStore; status: string; algorithm: string; currentRound: number; plannedRounds: number; accepted: number; expected: number;
	} = $props();
	const latest = $derived([...studio.records].filter((r) => r.evaluation_status === 'COMPLETED').sort((a, b) => b.round_id - a.round_id)[0]);
	const KEYS = [{ key: 'AUPRC', label: 'AUPRC' }, { key: 'AUROC', label: 'AUROC' }, { key: 'BCE', label: 'BCE', format: 'loss' as const }];
	const unavailable = $derived(Object.entries({
		'Unseen-cohort generalisation': ctx.capabilities.generalisation, 'Paired intervals': ctx.capabilities.pairedIntervals, 'Frozen V2 reference': ctx.capabilities.historicalReference
	}).filter(([, c]) => !c.available && !ctx.provisional));
	const LINKS = [['network', 'Clients'], ['evaluation', 'Evaluation'], ['graphs', 'Graphs'], ['analysis', 'Analysis'], ['timeline', 'Timeline']];
</script>
<section class="glance" aria-label="Run at a glance" data-testid="run-at-a-glance">
	<div class="top">
		<span class="badge" data-testid="source-badge">{ctx.badge}</span>
		<span class="mode">{ctx.execution === 'LIVE_TRAINING' ? 'Training executes now' : ctx.execution === 'EVENT_REPLAY' ? 'Event replay: no training' : ctx.execution === 'RECORDED_EVIDENCE' ? 'Stored historical record: nothing is trained' : 'Loading…'}</span>
	</div>
	<p class="what" data-testid="source-sentence">{ctx.dataSentence}</p>
	{#if ctx.startCandidate}<p class="what" data-testid="start-candidate">Starting model: stored engineering candidate <code>{ctx.startCandidate.id}</code>{ctx.startCandidate.cohort ? ` (trained on ${trainedOn(ctx.startCandidate.cohort)}${crossesCohorts(ctx.startCandidate.cohort, ctx.cohort) ? `; this run uses ${runCohortName(ctx.cohort)}` : ''})` : ''}. Round 0 is that candidate's final state, unchanged.</p>{/if}
	{#if ctx.startUntrained}<p class="what" data-testid="start-untrained">Starting model: the untrained V2 network (FL_INIT_V2). Round 0 is its seeded initial state; nothing is pretrained, so every weight is learned from your recorded windows and the seven synthetic peers.</p>{/if}
	<div class="cells">
		<div><span>STATUS</span><b data-testid="glance-status">{status}</b><small>round {Math.min(currentRound, plannedRounds || currentRound)} of {plannedRounds || '--'} · {accepted}/{expected} updates accepted</small></div>
		<div><span>METHOD</span><b>{algorithm}</b><small>{ctx.startCandidate ? 'stored candidate start' : ctx.startUntrained ? 'untrained V2 start' : ctx.lineage === 'MODEL_V2_FINAL' || ctx.lineage === 'HARDWARE_V2_PRETRAINED' ? 'pretrained V2 start' : ctx.lineage === 'FL_INIT_V2' ? 'untrained V2 architecture' : ctx.lineage === 'HARDWARE_DEMO_WARM_START' ? 'hardware model, warm start' : ctx.lineage === 'HARDWARE_DEMO_FRESH' ? 'hardware model, fresh start' : '—'}</small></div>
		{#if latest}
			{#each KEYS as k (k.key)}
				{@const d = display(latest, k.key, k.format)}
				<div><span>{k.label}</span><b data-testid={`glance-${k.key}`}>{d.tone === 'value' ? d.text : 'undefined'}</b><small>latest evaluated R{latest.round_id}</small></div>
			{/each}
		{:else}
			<div><span>RESULT</span><b data-testid="glance-no-result">—</b><small>no round has been evaluated yet</small></div>
		{/if}
	</div>
	<nav class="jump" aria-label="Jump to a section">{#each LINKS as [id, label] (id)}<a href={`#sec-${id}`}>{label}</a>{/each}</nav>
	{#if unavailable.length}
		<details class="na" data-testid="not-applicable"><summary>Not available for this run ({unavailable.length})</summary>
			<ul>{#each unavailable as [name, c] (name)}<li><b>{name}.</b> {c.reason}</li>{/each}</ul></details>
	{/if}
</section>
<style>
	.glance { border: 1px solid rgba(43,184,176,.35); background: rgba(8,32,31,.35); padding: 14px 16px; display: grid; gap: 10px; min-width: 0; }
	.top { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; } .badge { font: 600 12px 'JetBrains Mono', monospace; letter-spacing: .08em; color: #9fe7e1; border: 1px solid rgba(43,184,176,.6); padding: 3px 9px; }
	.mode { color: #cbd5e1; font-size: 13px; } .what { margin: 0; color: #cbd5e1; font-size: 14px; line-height: 1.55; max-width: 78ch; }
	.cells { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; } .cells div { border: 1px solid rgba(148,163,184,.18); padding: 8px 10px; display: grid; gap: 2px; min-width: 0; }
	.cells span { font: 11px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; } .cells b { font: 500 20px 'Space Grotesk', sans-serif; color: #e5f1f0; overflow-wrap: anywhere; } .cells small { color: #94a3b8; font-size: 12px; }
	.jump { display: flex; flex-wrap: wrap; gap: 6px 14px; } .jump a { color: #2bb8b0; font-size: 13px; min-height: 24px; display: inline-flex; align-items: center; }
	.na summary { cursor: pointer; color: #cbd5e1; font-size: 13px; min-height: 24px; } .na ul { margin: 6px 0 0; padding-left: 18px; color: #94a3b8; font-size: 13px; line-height: 1.55; } .na li { margin-bottom: 4px; }
</style>
