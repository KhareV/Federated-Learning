<script lang="ts">
	// Run facts, interpretation limits and the evidence boundary of THIS run (migrated from the retired FL10 overview cards; now available for every run).
	import DigestText from '$lib/components/product/federation/DigestText.svelte';
	import { useStudio } from '$lib/product/studio/store.svelte';
	import type { StudioStore } from '$lib/product/studio/store.svelte';
	let { studio }: { studio: StudioStore } = $props();
	const ov = $derived(studio.overview);
	const r = $derived(studio.selectedRound);
	const roundRow = $derived(ov?.rounds.find((x) => x.round === r) ?? null);
	const stateDigest = $derived(ov?.state_progression[String(r)] ?? null);
	const num = (v: unknown, d = 4) => (typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toFixed(d)) : 'NOT CAPTURED');
	const run = $derived((ov?.run ?? {}) as Record<string, unknown>);
	const candidate = $derived((run.candidate ?? null) as { candidate_id?: string; state_sha256?: string } | null);
	void useStudio;
</script>
<div class="ro" data-testid="run-overview">
	{#if !ov}<p class="dim" role="status">Loading run facts…</p>
	{:else}
		<p class="syn" data-testid="synthetic-label">{ov.synthetic_label}</p>{#if ov.live_label}<p class="syn live" data-testid="live-label">{ov.live_label}</p>{/if}
		<div class="cards" data-testid="overview-cards">
			<div><span>SOURCE</span><strong data-testid="source-label">{ov.source_label}</strong><small>{ov.source_mode} · {ov.run_id}</small></div>
			<div><span>STATUS</span><strong>{ov.status}</strong><small>weighted FedAvg · eight logical clients · {num(run.rounds_committed, 0)} of {ov.run_length} rounds committed</small></div>
			<div><span>ACCEPTED UPDATES</span><strong data-testid="accepted-updates">{num(run.accepted_updates_total, 0)}</strong><small>8 per round expected</small></div>
			<div><span>EXAMPLE EXPOSURES</span><strong>{num(run.example_exposures_total, 0)}</strong><small>{num(run.unique_training_windows, 0)} unique windows × {ov.run_length} rounds (repeated, not independent)</small></div>
			<div><span>FINAL CANDIDATE (R{ov.run_length})</span><strong class="mono">{candidate?.state_sha256 ? candidate.state_sha256.slice(0, 16) + '…' : 'NOT CREATED YET'}</strong><small>{candidate?.candidate_id ?? '—'} · not promoted · not deployed</small></div>
			<div><span>SELECTED STATE R{r}</span><strong class="mono">{stateDigest ? stateDigest.slice(0, 16) + '…' : 'NOT COMMITTED'}</strong><small>{roundRow ? `accepted ${roundRow.accepted_updates} · loss ${num(roundRow.weighted_mean_training_loss)} · ${num(roundRow.round_duration_seconds, 2)} s` : 'no committed round record'}</small></div>
			<div><span>EVALUATION COHORT</span><strong>{ov.evaluation.windows} windows</strong><small>16 participants · threshold {ov.evaluation.threshold} · no CAL_V2 · no round selection</small></div>
			<div><span>TIMING</span><strong>{run.total_seconds === null || run.total_seconds === undefined ? 'NOT CAPTURED' : `${num(run.total_seconds, 1)} s`}</strong><small>measured wall clock, single machine</small></div>
		</div>
		{#if ov.monitoring_link}<p class="dim" data-testid="monitoring-link">Source mode: {ov.monitoring_link.label}. Monitoring sessions executed: {ov.monitoring_link.monitoring_sessions_executed}; buffer reused for {ov.monitoring_link.buffer_reused_for_rounds} rounds. This is a simulated stream, not real physiology.</p>{/if}
		<details class="limits" open><summary>Interpretation limits</summary>
			<ul data-testid="limits">{#each ov.protocol.interpretation_boundaries ?? [] as l}<li>{l}</li>{/each}<li>Single-machine federation of eight logical clients on simulated data; payload bytes are logical serialized sizes, not network traffic.</li><li>{ov.evaluation.cohort_use_detail}</li></ul></details>
		<p class="dim">Protocol <code>{(ov.protocol.sha256 ?? '').slice(0, 16)}…</code> · holdout manifest <code>{(ov.protocol.holdout_manifest_sha256 ?? '').slice(0, 16)}…</code> · method freeze <code>{(ov.evaluation.method_freeze_commit ?? '').slice(0, 10)}</code> · separation proof: {ov.evaluation.separation_source}</p>
		{#if stateDigest}<p class="dim">Selected round state digest: <DigestText value={stateDigest} label={`round ${r} state digest`} /></p>{/if}
	{/if}
</div>
<style>
	.ro { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; min-width: 0; } .syn { display: inline-block; width: fit-content; border: 1px solid rgba(167,139,250,.6); padding: 5px 10px; color: #d8ccff; font: 11px 'JetBrains Mono', monospace; margin: 0 8px 0 0; } .syn.live { border-color: rgba(43,184,176,.7); color: #9fe8e3; }
	.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr)); gap: 8px; } .cards div { border: 1px solid rgba(148,163,184,.2); background: rgba(10,15,31,.6); padding: 9px 11px; display: grid; gap: 3px; min-width: 0; } .cards span { font: 9px 'JetBrains Mono', monospace; letter-spacing: .1em; color: #71829a; } .cards strong { font: 500 15px 'Space Grotesk', sans-serif; color: #e5f1f0; overflow-wrap: anywhere; } .cards strong.mono { font: 12px 'JetBrains Mono', monospace; } .cards small { color: #94a3b8; font-size: 11px; line-height: 1.45; }
	.dim { margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; } code { font: 11px 'JetBrains Mono', monospace; color: #9fe7e1; } .limits { border: 1px solid rgba(148,163,184,.2); padding: 8px 12px; } summary { cursor: pointer; font-size: 13px; color: #e2e8f0; } ul { margin: 6px 0 0; padding-left: 18px; display: grid; gap: 3px; } li { color: #cbd5e1; font-size: 12px; line-height: 1.55; }
	p, li, small, summary { overflow-wrap: anywhere; }
</style>
